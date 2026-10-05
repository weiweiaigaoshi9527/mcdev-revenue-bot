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

# 周末秒杀规则（取自开发者平台前端 calendar 组件）
FLASHSALE_MIN_ADVANCE = 9    # 最早可提前 9 天申请
FLASHSALE_MAX_ADVANCE = 22   # 最晚可提前 22 天申请
FLASHSALE_WEEKDAYS = (4, 5, 6)   # 周五 / 周六 / 周日
FLASHSALE_DEFAULT_QUOTA = 15     # 每日名额上限（接口返回会覆盖）


def _strip_html(text) -> str:
    """去掉活动描述里的 HTML 标签，便于在 QQ 里阅读。"""
    import re as _re

    s = str(text or "")
    s = _re.sub(r"<br\s*/?>", "\n", s, flags=_re.IGNORECASE)
    s = _re.sub(r"</p\s*>", "\n", s, flags=_re.IGNORECASE)
    s = _re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = _re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _to_date(value: str) -> date:
    """把 ``YYYYMMDD`` 或 ``YYYY-MM-DD`` 解析为 date。"""
    s = str(value or "").replace("-", "").strip()
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def _fmt_ts(value) -> str:
    """把平台的时间戳（秒）转成 ``YYYY-MM-DD``；已是文本则原样返回。"""
    s = str(value or "").strip()
    if not s:
        return ""
    if s.isdigit() and len(s) >= 9:      # Unix 秒级时间戳
        try:
            return datetime.fromtimestamp(int(s)).strftime("%Y-%m-%d")
        except (ValueError, OSError, OverflowError):
            return s
    return _fmt_iso(s)


def _fmt_iso(s: str) -> str:
    """把 ISO 时间或 YYYYMMDD 统一成 YYYY-MM-DD。"""
    s = s.strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


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

    async def balance(self) -> Dict[str, object]:
        """账户余额（平台 ``users/me`` 口径 + 结算单补充）。

        平台账号信息（``users/me``）里直接带着两个官方数值：
            income             我的收益（元）
            unextract_income   未提取收益（元）

        返回 dict：
            income_rmb      我的收益（元，平台口径）
            unextract_rmb   未提取收益（元，平台口径）
            pay_type        结算方式标识（如 individual_withhold）
            bank / card_no  收款账户
            deposit         保证金（元）
            incentive_fund  当月鼓励金（元）
            income_limit    收益是否受限
            settled_rmb     官方结算单累计收益（元）
            settled_count   已出账月份数
            last_month      最近出账月份
            last_income     最近出账月份的收益（元）
            last_status     最近结算状态（平台字段 status）
            total_diamond   累计消耗钻石
        """
        info = await self.client.get_user_info()
        if not isinstance(info, dict):
            info = {}

        def money(key: str) -> float:
            try:
                return round(float(info.get(key) or 0), 2)
            except (TypeError, ValueError):
                return 0.0

        records = await self.settlements()
        latest = records[0] if records else None

        return {
            "income_rmb": money("income"),
            "unextract_rmb": money("unextract_income"),
            "deposit": money("deposit"),
            "incentive_fund": money("cur_month_incentive_fund"),
            "income_limit": bool(info.get("income_limit")),
            "pay_type": str(info.get("pay_type") or ""),
            "bank": str(info.get("bank") or ""),
            "card_no": str(info.get("card_no") or ""),
            "settled_rmb": round(sum(r.income for r in records), 2),
            "settled_count": len(records),
            "last_month": latest.data_month if latest else "",
            "last_income": round(float(latest.income), 2) if latest else 0.0,
            "last_status": str((latest.raw.get("status") if latest else "") or ""),
            "total_diamond": int(latest.total_diamond) if latest else 0,
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

    # ------------------------------------------------------------------
    # 玩家反馈 / 退款
    # ------------------------------------------------------------------
    async def feedback_list(self, span: int = 50) -> List[Dict[str, object]]:
        """玩家反馈列表（按时间倒序）。"""
        rows = await self.client.get_feedback_list(span=span)
        out: List[Dict[str, object]] = []
        for r in rows:
            out.append({
                "id": str(r.get("_id") or r.get("id") or ""),
                "item_name": str(r.get("res_name") or r.get("item_name") or ""),
                "content": str(r.get("feedback_content") or r.get("content") or ""),
                "contact": str(r.get("contact") or ""),
                "status": r.get("status"),
                "reply": str(r.get("reply_content") or r.get("reply") or ""),
                "create_time": str(r.get("create_time") or r.get("op_time") or ""),
                "raw": r,
            })
        return out

    async def refund_bills(self, start: str = "", end: str = "", span: int = 200) -> Dict[str, object]:
        """退款账单 + 退款率。

        退款率 = 退款笔数 ÷ 同期成交笔数（以 day_detail 的 cnt_buy 为分母）。
        """
        rows = await self.client.get_refund_reasons(start=start, end=end, span=span)
        bills: List[Dict[str, object]] = []
        by_item: Dict[str, int] = {}
        for r in rows:
            name = str(r.get("res_name") or r.get("item_name") or "未知作品")
            by_item[name] = by_item.get(name, 0) + 1
            bills.append({
                "item_name": name,
                "iid": str(r.get("iid") or ""),
                "platform": str(r.get("platform") or ""),
                "refund_time": str(r.get("refund_time") or ""),
                "reason": str(r.get("refund_reason") or ""),
                "remarks": str(r.get("refund_remarks") or ""),
            })

        # 分母：同区间成交笔数
        sold = 0
        try:
            if start and end:
                rows_d = await self.daily_between(_to_date(start), _to_date(end))
                sold = sum(int(d.cnt_buy or 0) for d in rows_d)
        except Exception:  # noqa: BLE001  分母取不到则退款率留空
            sold = 0

        count = len(bills)
        rate = round(count / sold * 100, 2) if sold > 0 else None
        return {
            "count": count,
            "sold": sold,
            "rate": rate,
            "bills": bills,
            "by_item": sorted(by_item.items(), key=lambda kv: kv[1], reverse=True),
        }

    # ------------------------------------------------------------------
    # 运营数据（日活 / 涨粉 / 人均游玩时长 / 退款率）
    # ------------------------------------------------------------------
    async def analytics(self, days: int = 7, end: Optional[date] = None) -> Dict[str, object]:
        """按作品聚合运营指标：日活、组件涨粉、人均游玩时长、退款率。"""
        end = end or self.latest_day
        days = max(1, int(days))
        start = end - timedelta(days=days - 1)
        rows = await self._fetch(start, end)

        def num(value) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        per_item: Dict[str, Dict[str, float]] = {}
        total_dau = 0.0
        total_focus = 0.0
        play_weighted = 0.0
        play_days = 0
        refund_sum = 0.0
        refund_n = 0

        for r in rows:
            raw = r.raw or {}
            iid = r.iid or r.res_name
            dau = num(r.dau)
            focus = num(raw.get("focus_cnt"))
            play = num(raw.get("avg_playtime"))
            rr = num(r.refund_rate)

            total_dau += dau
            total_focus += focus
            if play > 0:
                play_weighted += play
                play_days += 1
            refund_sum += rr
            refund_n += 1

            bucket = per_item.setdefault(
                iid, {"name": r.res_name or "", "dau": 0.0, "focus": 0.0,
                      "play_sum": 0.0, "play_n": 0, "refund_sum": 0.0, "refund_n": 0},
            )
            bucket["name"] = bucket["name"] or (r.res_name or "")
            bucket["dau"] += dau
            bucket["focus"] += focus
            if play > 0:
                bucket["play_sum"] += play
                bucket["play_n"] += 1
            bucket["refund_sum"] += rr
            bucket["refund_n"] += 1

        items = []
        for iid, b in per_item.items():
            items.append({
                "iid": iid,
                "name": b["name"],
                "dau_avg": round(b["dau"] / days, 1),
                "focus": int(b["focus"]),
                "play_avg": round(b["play_sum"] / b["play_n"], 1) if b["play_n"] else 0.0,
                "refund_rate": round(b["refund_sum"] / b["refund_n"], 2) if b["refund_n"] else 0.0,
            })
        items.sort(key=lambda x: x["dau_avg"], reverse=True)

        return {
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "days": days,
            "dau_avg": round(total_dau / days, 1),
            "focus_total": int(total_focus),
            "play_avg": round(play_weighted / play_days, 1) if play_days else 0.0,
            "refund_rate": round(refund_sum / refund_n, 2) if refund_n else 0.0,
            "items": items,
        }

    # ------------------------------------------------------------------
    # 活动（征集 / 折扣特卖 / 联动）
    # ------------------------------------------------------------------
    async def activities(self) -> Dict[str, object]:
        """当前活动：模组征集、折扣特卖、优惠券、官方联动。"""
        review: List[Dict[str, object]] = []
        try:
            for a in await self.client.get_review_activities():
                review.append({
                    "id": str(a.get("activity_id") or ""),
                    "name": str(a.get("activity_name") or ""),
                    "desc": _strip_html(a.get("activity_description")),
                    "instruction": _strip_html(a.get("activity_instruction")),
                    "begin_at": _fmt_ts(a.get("begin_at")),
                    "end_at": _fmt_ts(a.get("end_at")),
                    "apply_end_at": _fmt_ts(a.get("apply_end_at")),
                    "modules": a.get("activity_modules") or [],
                    "raw": a,
                })
        except Exception:  # noqa: BLE001
            review = []

        # 按活动结束时间倒序（最新的活动排在前面）
        review.sort(key=lambda x: str(x.get("end_at") or ""), reverse=True)

        # 未结束的活动（今天仍在进行或即将开始）
        today_str = date.today().strftime("%Y-%m-%d")
        active = [
            a for a in review
            if not a.get("end_at") or str(a.get("end_at")) >= today_str
        ]

        discount: Dict[str, object] = {}
        try:
            d = await self.client.get_discount_activity()
            if d:
                discount = {
                    "id": str(d.get("activity_id") or ""),
                    "name": str(d.get("activity_name") or ""),
                    "desc": _strip_html(d.get("activity_description")),
                    "instruction": _strip_html(d.get("activity_instruction")),
                    "begin_at": _fmt_ts(d.get("begin_at")),
                    "end_at": _fmt_ts(d.get("end_at")),
                    "status": d.get("status"),
                    "modules": d.get("activity_modules") or [],
                }
        except Exception:  # noqa: BLE001
            discount = {}

        coupons: List[dict] = []
        try:
            coupons = await self.client.get_coupon_activity()
        except Exception:  # noqa: BLE001
            coupons = []

        return {"review": review, "active": active, "discount": discount, "coupons": coupons}

    # ------------------------------------------------------------------
    # 周末秒杀
    # ------------------------------------------------------------------
    async def flashsale_dates(self) -> Dict[str, object]:
        """可参与周末秒杀的日期（提前 9~22 天、周五六日、名额未满）。"""
        today = date.today()
        min_day = today + timedelta(days=FLASHSALE_MIN_ADVANCE)
        max_day = today + timedelta(days=FLASHSALE_MAX_ADVANCE)

        candidates: List[date] = []
        cur = min_day
        while cur <= max_day:
            if cur.weekday() in FLASHSALE_WEEKDAYS:  # 4=周五 5=周六 6=周日
                candidates.append(cur)
            cur += timedelta(days=1)

        quota_limit = FLASHSALE_DEFAULT_QUOTA
        used: Dict[str, int] = {}
        try:
            info = await self.client.get_flashsale_quota([d.strftime("%Y%m%d") for d in candidates])
            if isinstance(info.get("daily_quota"), int) and info["daily_quota"] >= 0:
                quota_limit = int(info["daily_quota"])
            if isinstance(info.get("res_info"), dict):
                used = {str(k): int(v) for k, v in info["res_info"].items()}
        except Exception:  # noqa: BLE001  名额查不到就按上限展示
            used = {}

        out = []
        for d in candidates:
            key = d.strftime("%Y%m%d")
            u = used.get(key, 0)
            out.append({
                "date": key,
                "label": f"{d.strftime('%Y-%m-%d')}（周{'一二三四五六日'[d.weekday()]}）",
                "used": u,
                "left": max(quota_limit - u, 0),
                "full": u >= quota_limit,
            })

        return {
            "today": today.strftime("%Y-%m-%d"),
            "window": f"{min_day.strftime('%Y-%m-%d')} ~ {max_day.strftime('%Y-%m-%d')}",
            "quota": quota_limit,
            "dates": out,
        }

    async def flashsale_history(self) -> List[Dict[str, object]]:
        """秒杀申请历史。"""
        rows = await self.client.get_flashsale_history()
        out = []
        for r in rows:
            out.append({
                "date": str(r.get("date") or ""),
                "item_id": str(r.get("item_id") or ""),
                "item_name": str(r.get("item_name") or ""),
                "num": r.get("flashsale_num"),
                "price": r.get("flashsale_price"),
                "status": r.get("status"),
                "create_time": str(r.get("create_time") or ""),
            })
        out.sort(key=lambda x: x["create_time"], reverse=True)
        return out

    async def apply_flashsale(self, item_id: str, date: str, num: int = 1000) -> Dict[str, object]:
        """提交周末秒杀申请。"""
        return await self.client.apply_flashsale(item_id=item_id, date=date, num=num)


__all__ = ["RevenueService", "Overview", "build_client", "MAX_MONTHS"]
