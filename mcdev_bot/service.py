"""业务聚合层。

口径说明（已用真实账号与平台 overview 接口逐项校验一致）：
  · 以 ``data_analysis/day_detail/`` 的逐日数据为权威来源，按作品/日期聚合；
  · 「是否统计今天」与平台保持一致 —— 平台只出到「昨天」，因此本项目默认也不含今天；
  · 日均 = 区间收益 / 区间自然天数（与平台 14 天日均的算法一致）。
  · 月报按「逐月单独查询再聚合」实现，避免超长区间可能带来的返回不全。
"""
from __future__ import annotations

import calendar
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .client import McDevClient, McDevError
from .config import Settings, settings as default_settings
from .mock import MockClient
from .models import DailyRow, ItemSummary, MapRevenue, MonthRevenue, Settlement
from .profile import DeveloperProfile, fetch_profile
from .revenue import build_breakdown

MAX_MONTHS = 12  # 月报最多回溯的月份数


def build_client(config: Optional[Settings] = None):
    """按配置返回真实客户端或演示客户端。"""
    cfg = config or default_settings
    if cfg.use_mock:
        return MockClient(cfg)
    return McDevClient(cfg)


@dataclass
class Overview:
    """某个时间范围的总体概览。"""

    start_date: str = ""
    end_date: str = ""
    days: int = 0
    total_diamond: int = 0
    total_sales: int = 0
    total_pay_role: int = 0
    total_download: int = 0
    items_count: int = 0
    maps: List[MapRevenue] = field(default_factory=list)

    @property
    def daily_avg_diamond(self) -> float:
        return round(self.total_diamond / self.days, 2) if self.days else 0.0

    @property
    def daily_avg_sales(self) -> float:
        return round(self.total_sales / self.days, 2) if self.days else 0.0


class RevenueService:
    """所有统计口径的统一入口。"""

    def __init__(self, client, config: Optional[Settings] = None) -> None:
        self.client = client
        self.cfg = config or default_settings
        self._item_ids: Optional[List[str]] = None
        self._items: Optional[List[ItemSummary]] = None
        self._profile: Optional[DeveloperProfile] = None
        self._eco_rate: Optional[float] = None

    # ------------------------------------------------------------------
    # 时间与作品
    # ------------------------------------------------------------------
    @property
    def latest_day(self) -> date:
        """平台数据只出到昨天。"""
        return date.today() - timedelta(days=1)

    async def items(self) -> List[ItemSummary]:
        """名下作品列表。"""
        if self._items is None:
            self._items = await self.client.get_items()
        return self._items

    async def profile(self) -> DeveloperProfile:
        """当前登录开发者的昵称 / 头像等资料。"""
        if self._profile is None:
            self._profile = await fetch_profile(self.client)
        return self._profile

    async def _ids(self) -> List[str]:
        if self._item_ids is None:
            items = await self.items()
            ids = [i.item_id for i in items if i.item_id]
            if not ids:
                raise McDevError("该账号下暂无可统计的作品（或当前分类无权限）")
            self._item_ids = ids
        return self._item_ids

    # ------------------------------------------------------------------
    # 内部聚合
    # ------------------------------------------------------------------
    def _match(self, name: str) -> bool:
        keyword = self.cfg.item_keyword
        return (not keyword) or (keyword in (name or ""))

    async def _fetch(self, start: date, end: date) -> List[DailyRow]:
        if end < start:
            return []
        ids = await self._ids()
        rows = await self.client.get_day_detail(start, end, item_ids=ids)
        return [r for r in rows if r.dateid]

    def _aggregate(self, rows: List[DailyRow], days: int, start: date, end: date) -> Overview:
        buckets: "OrderedDict[str, MapRevenue]" = OrderedDict()
        for row in rows:
            if not self._match(row.res_name):
                continue
            key = row.iid or row.res_name
            item = buckets.get(key)
            if item is None:
                item = MapRevenue(iid=key, name=row.res_name or "未命名作品")
                buckets[key] = item
            item.diamond += row.diamond
            item.sales += row.cnt_buy
            item.pay_role += row.pay_role
            item.download_num += row.download_num

        ov = Overview(start_date=start.strftime("%Y-%m-%d"),
                      end_date=end.strftime("%Y-%m-%d"),
                      days=max(days, 1))
        for item in buckets.values():
            item.days = ov.days
            ov.total_diamond += item.diamond
            ov.total_sales += item.sales
            ov.total_pay_role += item.pay_role
            ov.total_download += item.download_num
        ov.items_count = len(buckets)
        ov.maps = sorted(buckets.values(), key=lambda m: m.diamond, reverse=True)
        return ov

    # ------------------------------------------------------------------
    # 对外口径
    # ------------------------------------------------------------------
    async def overview(self, days: int = 7, end: Optional[date] = None) -> Overview:
        """最近 N 天总览（默认截至昨天）。"""
        end = end or self.latest_day
        days = max(1, int(days))
        start = end - timedelta(days=days - 1)
        rows = await self._fetch(start, end)
        return self._aggregate(rows, days, start, end)

    async def per_map(self, days: int = 7, end: Optional[date] = None) -> Overview:
        """各地图/作品收益与销量（同 overview，语义化别名）。"""
        return await self.overview(days=days, end=end)

    async def yesterday(self) -> Overview:
        """昨日收益。"""
        target = self.latest_day
        rows = await self._fetch(target, target)
        return self._aggregate(rows, 1, target, target)

    async def latest_available(self, lookback: int = 3) -> Overview:
        """最近一个「有数据」的日期。

        平台数据存在发布延迟：刚过零点时，昨天的数据往往还没出。
        定时推送用它可避免推出一条全 0 的消息。
        """
        for offset in range(1, lookback + 2):
            day = date.today() - timedelta(days=offset)
            rows = await self._fetch(day, day)
            ov = self._aggregate(rows, 1, day, day)
            if ov.total_diamond or ov.total_sales or ov.total_download:
                return ov
        return await self.yesterday()

    async def daily_average(self, days: int = 7, end: Optional[date] = None) -> Overview:
        """日均收益（区间总收益 / 区间自然天数）。"""
        return await self.overview(days=days, end=end)

    async def daily_between(self, start: date, end: Optional[date] = None) -> List[DailyRow]:
        """指定区间的每日汇总（按日期合并所有作品，并补全无数据的日期）。"""
        end = end or self.latest_day
        if end < start:
            start, end = end, start
        rows = await self._fetch(start, end)

        merged: "OrderedDict[str, DailyRow]" = OrderedDict()
        for row in rows:
            if not self._match(row.res_name):
                continue
            target = merged.get(row.dateid)
            if target is None:
                merged[row.dateid] = DailyRow(
                    dateid=row.dateid, res_name="全部作品", diamond=row.diamond,
                    cnt_buy=row.cnt_buy, pay_role=row.pay_role,
                    download_num=row.download_num, dau=row.dau,
                )
            else:
                target.diamond += row.diamond
                target.cnt_buy += row.cnt_buy
                target.pay_role += row.pay_role
                target.download_num += row.download_num
                target.dau += row.dau
        # 补齐没有数据的日期，保证趋势连续
        cursor = start
        while cursor <= end:
            key = cursor.strftime("%Y%m%d")
            merged.setdefault(key, DailyRow(dateid=key, res_name="全部作品"))
            cursor += timedelta(days=1)
        return [merged[k] for k in sorted(merged)]

    async def recent_daily(self, days: int = 7, end: Optional[date] = None) -> List[DailyRow]:
        """最近 N 天的每日汇总。"""
        end = end or self.latest_day
        days = max(1, int(days))
        return await self.daily_between(end - timedelta(days=days - 1), end)

    def trend_start_date(self) -> date:
        """趋势图起始日期：取配置值，未配置则默认最近 90 天。"""
        raw = (self.cfg.trend_start or "").strip()
        if raw:
            text = raw.replace("/", "-")
            for fmt in ("%Y%m%d", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt).date()
                except ValueError:
                    continue
        return self.latest_day - timedelta(days=89)

    async def trend_daily(self) -> List[DailyRow]:
        """从配置的起始日期（如作品上线日）到最新可用日期的完整趋势。"""
        return await self.daily_between(self.trend_start_date())

    async def trend_overview(self) -> Overview:
        """起始日 → 最新可用日期的总览（与 trend_daily 同区间）。"""
        start = self.trend_start_date()
        end = self.latest_day
        days = max((end - start).days + 1, 1)
        return await self.overview(days=days, end=end)

    async def monthly(self, months: int = 6) -> List[MonthRevenue]:
        """各月钻石收益（逐月查询 day_detail 后聚合，并按规则推算收益）。"""
        months = max(1, min(int(months), MAX_MONTHS))
        today = self.latest_day
        eco_rate = await self.ecosystem_cost_rate()

        periods: List[tuple] = []
        y, m = today.year, today.month
        for _ in range(months):
            periods.append((y, m))
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        periods.reverse()

        result: List[MonthRevenue] = []
        for (yy, mm) in periods:
            first = date(yy, mm, 1)
            last = date(yy, mm, calendar.monthrange(yy, mm)[1])
            end = min(last, today)
            if end < first:
                continue
            rows = await self._fetch(first, end)
            span_days = (end - first).days + 1
            ov = self._aggregate(rows, span_days, first, end)
            # 按最新分成规则推算（生态成本比例自动按官方结算校准）
            bd = build_breakdown(
                ov.total_diamond, eco_rate, incentive_rate=self.cfg.incentive_rate
            )
            result.append(
                MonthRevenue(
                    monthid=f"{yy}{mm:02d}",
                    total_diamond=ov.total_diamond,
                    developer_share=bd.share_diamonds,
                    share_rmb=bd.share_rmb,
                    incentive_rmb=bd.incentive_rmb,
                    share_ratio=bd.ratio,
                    sharable=bd.sharable,
                    sales=ov.total_sales,
                    days=span_days,
                    maps=ov.maps,
                )
            )
        result.reverse()  # 最新的月份在前
        return result

    async def settlements(self) -> List[Settlement]:
        """平台官方结算记录（真实数值，按自然月倒序）。"""
        records = await self.client.get_settlements()
        return sorted(records, key=lambda s: s.data_month, reverse=True)

    async def ecosystem_cost_rate(self) -> float:
        """生效的生态成本分摊比例。

        优先用配置值 ``MCDEV_ECOSYSTEM_COST_RATE``；未配置（0）时自动按官方结算反推，
        这样「规则推算」会随官方数据自动校准。
        """
        if self.cfg.ecosystem_cost_rate > 0:
            return self.cfg.ecosystem_cost_rate
        if self._eco_rate is None:
            rate = 0.0
            try:
                records = await self.settlements()
                if records:
                    rate = records[0].ecosystem_cost_rate
            except Exception:  # noqa: BLE001  取不到就退回 0
                rate = 0.0
            self._eco_rate = rate
        return self._eco_rate

    async def settled_income(self) -> float:
        """累计已结算收益（元），取官方结算记录之和。"""
        records = await self.settlements()
        return round(sum(s.income for s in records), 2)

    async def income_summary(self, months: int = 6) -> Dict[str, object]:
        """收益汇总：官方已结算 + 未结算月份的预估。

        返回 dict：
            settled_rmb     官方已结算收益（元）
            pending_rmb     未结算月份的预估收益（元）
            total_rmb       预计实际收益合计（元）
            settled_months  已结算月份
            pending_months  未结算（但有流水）的月份
            eco_rate        生效的生态成本比例
        """
        records = await self.settlements()
        settled_months = [r.data_month for r in records]
        settled_keys = {m.replace("-", "") for m in settled_months}
        settled_rmb = round(sum(r.income for r in records), 2)

        rows = await self.monthly(months=months)
        pending = [m for m in rows if m.monthid not in settled_keys and m.total_diamond > 0]
        pending_rmb = round(sum(m.income_rmb for m in pending), 2)

        return {
            "settled_rmb": settled_rmb,
            "pending_rmb": pending_rmb,
            "total_rmb": round(settled_rmb + pending_rmb, 2),
            "settled_months": settled_months,
            "pending_months": [m.monthid for m in pending],
            "eco_rate": await self.ecosystem_cost_rate(),
        }

    async def account_overview(self) -> Dict[str, int]:
        """平台账号级总览（官方口径，用于状态页/补充信息）。"""
        data = await self.client.get_overview()
        keys = (
            "yesterday_diamond", "yesterday_download",
            "days_14_total_diamond", "days_14_average_diamond",
            "days_14_total_download", "days_14_average_download",
            "this_month_diamond", "last_month_diamond",
            "this_month_download", "last_month_download",
        )
        out: Dict[str, int] = {}
        for k in keys:
            try:
                out[k] = int(data.get(k) or 0)
            except (TypeError, ValueError):
                out[k] = 0
        return out


__all__ = ["RevenueService", "Overview", "build_client", "MAX_MONTHS"]
