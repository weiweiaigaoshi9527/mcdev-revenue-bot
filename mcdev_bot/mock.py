"""演示 / 离线数据源。

未配置 Cookie 时，机器人自动切换到本模块，保证开箱即可对话验证功能。
生成的数据是「确定性伪随机」的：同一作品同一天结果固定，便于测试。
接口签名与 :class:`mcdev_bot.client.McDevClient` 保持一致。
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import List, Optional, Union

from .models import DailyRow, ItemSummary, MonthlyRow, Settlement

# 演示用作品（地图 / 组件）
_MOCK_MAPS = [
    ("100001", "天空之城 · 生存地图", 1200),
    ("100002", "密室逃脱 · 古堡惊魂", 900),
    ("100003", "极限跑酷 · 都市天际线", 600),
    ("100004", "冰火世界 · 空岛战争", 800),
    ("100005", "建筑大师 · 现代都市", 1500),
]

DateLike = Union[str, date, datetime]


def _to_date(value: DateLike) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return date.today()


def _seed(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:8], 16)


def _rand(lo: int, hi: int, *parts: object) -> int:
    if hi <= lo:
        return lo
    return lo + _seed(*parts) % (hi - lo + 1)


class MockClient:
    """与 :class:`McDevClient` 接口一致的演示数据源。"""

    def __init__(self, config=None) -> None:
        self.cfg = config

    async def aclose(self) -> None:
        return None

    async def check_login(self) -> bool:
        return True

    async def get_user_info(self) -> dict:
        return {"nickname": "演示开发者", "developer_name": "Demo Studio"}

    async def get_items(self, category: Optional[str] = None) -> List[ItemSummary]:
        return [
            ItemSummary(item_id=iid, item_name=name, price=price, price_type="diamond", status="online")
            for iid, name, price in _MOCK_MAPS
        ]

    async def get_item_ids(self, category: Optional[str] = None) -> List[str]:
        return [iid for iid, _, _ in _MOCK_MAPS]

    async def get_overview(self) -> dict:
        today = date.today()
        y = today - timedelta(days=1)
        y14 = [y - timedelta(days=i) for i in range(14)]
        total14 = sum(sum(self._day_value(iid, d) for iid, _, _ in _MOCK_MAPS) for d in y14)
        month_start = today.replace(day=1)
        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        def month_total(start: date, end: date) -> int:
            total = 0
            cursor = start
            while cursor <= end:
                total += sum(self._day_value(iid, cursor) for iid, _, _ in _MOCK_MAPS)
                cursor += timedelta(days=1)
            return total

        return {
            "yesterday_diamond": sum(self._day_value(iid, y) for iid, _, _ in _MOCK_MAPS),
            "days_14_total_diamond": total14,
            "days_14_average_diamond": round(total14 / 14),
            "last_month_diamond": month_total(last_month_start, last_month_end),
            "this_month_diamond": month_total(month_start, y),
        }

    def _day_value(self, iid: str, day: date) -> int:
        key_day = day.strftime("%Y%m%d")
        base = _rand(30, 220, "base", iid)
        wave = _rand(-15, 25, "wave", iid, key_day)
        sales = max(0, base + wave)
        price = _rand(600, 1500, "price", iid)
        return sales * price

    def _day_rows(self, start: date, end: date) -> List[DailyRow]:
        if end < start:
            start, end = end, start
        rows: List[DailyRow] = []
        day = start
        while day <= end:
            key_day = day.strftime("%Y%m%d")
            for iid, name, _ in _MOCK_MAPS:
                base = _rand(30, 220, "base", iid)
                wave = _rand(-15, 25, "wave", iid, key_day)
                sales = max(0, base + wave)
                price = _rand(600, 1500, "price", iid)
                rows.append(
                    DailyRow(
                        dateid=key_day,
                        iid=iid,
                        res_name=name,
                        game_name=name,
                        diamond=sales * price,
                        cnt_buy=sales,
                        pay_role=sales,
                        download_num=sales * _rand(3, 9, "dl", iid, key_day),
                        dau=_rand(800, 6000, "dau", iid, key_day),
                        refund_rate=round(_rand(0, 300, "ref", iid, key_day) / 10000, 4),
                    )
                )
            day += timedelta(days=1)
        return rows

    async def get_day_detail(
        self,
        start_date: DateLike,
        end_date: DateLike,
        item_ids: Union[str, List[str]] = "",
        platform: Optional[str] = None,
        category: Optional[str] = None,
        sort: str = "dateid",
        order: str = "ASC",
        span: int = 200000,
        start: int = 0,
    ) -> List[DailyRow]:
        rows = self._day_rows(_to_date(start_date), _to_date(end_date))
        if item_ids:
            ids = item_ids if isinstance(item_ids, (list, tuple)) else str(item_ids).split(",")
            wanted = {str(i).strip() for i in ids if str(i).strip()}
            if wanted:
                rows = [r for r in rows if r.iid in wanted]
        return rows

    async def get_month_detail(
        self,
        start_date: DateLike,
        end_date: DateLike,
        item_ids: Union[str, List[str]] = "",
        **kwargs,
    ) -> List[MonthlyRow]:
        begin, end = _to_date(start_date), _to_date(end_date)
        rows: List[MonthlyRow] = []
        cursor = begin.replace(day=1)
        while cursor <= end:
            monthid = cursor.strftime("%Y%m%d")
            for iid, name, _ in _MOCK_MAPS:
                sales = _rand(500, 4500, "msale", iid, monthid[:6])
                price = _rand(600, 1500, "mprice", iid)
                rows.append(
                    MonthlyRow(
                        monthid=monthid, iid=iid, res_name=name,
                        total_diamond=sales * price, cnt_buy=sales,
                    )
                )
            cursor = (cursor + timedelta(days=32)).replace(day=1)
        return rows

    async def get_settlements(self, platform: Optional[str] = None) -> List[Settlement]:
        """演示用官方结算记录（按平台真实字段结构生成）。"""
        today = date.today()
        result: List[Settlement] = []
        for offset in range(1, 4):
            m, y = today.month - offset, today.year
            while m <= 0:
                m += 12
                y -= 1
            month_key = f"{y}{m:02d}"
            total = sum(
                _rand(500, 4500, "msale", iid, month_key) * _rand(600, 1500, "mprice", iid)
                for iid, _, _ in _MOCK_MAPS
            )
            sharable = round(total * 0.66, 2)
            share = round(sharable * 0.5, 2)
            share_rmb = round(share * 0.01, 2)
            incentive = share_rmb
            result.append(
                Settlement(
                    data_month=f"{y}-{m:02d}",
                    platform="pe",
                    income=round(share_rmb + incentive, 2),
                    available_income=0.0,
                    total_diamond=total,
                    sharable_flow=sharable,
                    developer_share=share,
                    incentive_income=incentive,
                    exchange_rate=0.01,
                    op_time=f"{y}-{m:02d}-10T01:30:00+00:00",
                    type="individual_withhold",
                )
            )
        return result

    async def get_item_incomes(self, item_id: str) -> List[dict]:
        return [s.raw or {"data_month": s.data_month, "income": s.income}
                for s in await self.get_settlements()]


__all__ = ["MockClient"]
