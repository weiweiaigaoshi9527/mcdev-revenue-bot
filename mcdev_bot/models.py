"""数据模型。

字段名严格对应开发者平台接口返回的真实字段：
  - 日/月分析：data_analysis{prefix}day_detail/ 、 month_detail/
  - 作品汇总：goods/{platform}/summary
  - 收益结算：incomes/ 、 items/categories/{cate}/{id}/incomes/
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


def _to_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class DailyRow:
    """data_analysis/{...}/day_detail/ 的单条记录。

    对应前端表格字段：dateid, iid, game_id, game_name, res_name, cnt_buy,
    download_num, diamond, pay_role, DAU, avg_playtime, refund_rate ...
    """

    dateid: str = ""
    iid: str = ""
    res_name: str = ""
    game_name: str = ""
    diamond: int = 0          # 当日钻石收益
    cnt_buy: int = 0          # 当日销量（购买数）
    pay_role: int = 0         # 付费人数
    download_num: int = 0     # 下载数
    dau: int = 0              # 日活
    refund_rate: float = 0.0  # 退款率
    raw: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, obj: dict) -> "DailyRow":
        return cls(
            dateid=str(obj.get("dateid") or ""),
            iid=str(obj.get("iid") or obj.get("item_id") or ""),
            res_name=str(obj.get("res_name") or obj.get("item_name") or ""),
            game_name=str(obj.get("game_name") or obj.get("name") or ""),
            diamond=_to_int(obj.get("diamond")),
            cnt_buy=_to_int(obj.get("cnt_buy")),
            pay_role=_to_int(obj.get("pay_role")),
            download_num=_to_int(obj.get("download_num")),
            dau=_to_int(obj.get("DAU", obj.get("dau"))),
            refund_rate=_to_float(obj.get("refund_rate")),
            raw=obj,
        )


@dataclass
class MonthlyRow:
    """data_analysis/{...}/month_detail/ 的单条记录。

    对应前端表格字段：monthid, iid, res_name, total_diamond, sharable_flow,
    developer_share, cnt_buy, download_num, avg_dau, avg_day_buy, mau ...
    """

    monthid: str = ""
    iid: str = ""
    res_name: str = ""
    total_diamond: int = 0       # 当月总钻石流水
    sharable_flow: int = 0       # 可分成钻石流水
    developer_share: int = 0     # 开发者分成（钻石）
    cnt_buy: int = 0             # 当月销量
    download_num: int = 0        # 当月下载
    avg_day_buy: int = 0         # 日均购买
    avg_dau: int = 0             # 日均活跃
    raw: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, obj: dict) -> "MonthlyRow":
        return cls(
            monthid=str(obj.get("monthid") or obj.get("data_month") or ""),
            iid=str(obj.get("iid") or obj.get("item_id") or ""),
            res_name=str(obj.get("res_name") or obj.get("item_name") or ""),
            total_diamond=_to_int(obj.get("total_diamond")),
            sharable_flow=_to_int(obj.get("sharable_flow")),
            developer_share=_to_int(obj.get("developer_share")),
            cnt_buy=_to_int(obj.get("cnt_buy")),
            download_num=_to_int(obj.get("download_num")),
            avg_day_buy=_to_int(obj.get("avg_day_buy")),
            avg_dau=_to_int(obj.get("avg_dau")),
            raw=obj,
        )


@dataclass
class ItemSummary:
    """items/categories/{cate}/ 的单条记录（作品维度信息）。

    对应平台返回字段：item_id, item_name, price, price_type, status, create_time...
    """

    item_id: str = ""
    item_name: str = ""
    price: int = 0
    price_type: str = ""
    status: str = ""
    create_time: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, obj: dict) -> "ItemSummary":
        return cls(
            item_id=str(obj.get("item_id") or obj.get("iid") or obj.get("id") or ""),
            item_name=str(
                obj.get("item_name") or obj.get("name") or obj.get("res_name") or "未命名作品"
            ),
            price=_to_int(obj.get("price")),
            price_type=str(obj.get("price_type") or ""),
            status=str(obj.get("status") or obj.get("item_real_status") or ""),
            create_time=str(obj.get("create_time") or ""),
            raw=obj,
        )


@dataclass
class MapRevenue:
    """单张地图（作品）在指定统计口径下的收益与销量。"""

    iid: str
    name: str
    diamond: int = 0            # 钻石收益
    sales: int = 0              # 销量
    pay_role: int = 0           # 付费人数
    download_num: int = 0       # 下载量
    days: int = 0               # 统计天数（用于日均）
    developer_share: int = 0    # 可分成收益

    @property
    def daily_avg_diamond(self) -> float:
        return round(self.diamond / self.days, 2) if self.days else 0.0

    @property
    def daily_avg_sales(self) -> float:
        return round(self.sales / self.days, 2) if self.days else 0.0


@dataclass
class Settlement:
    """平台官方结算记录（``incomes/`` 接口，按自然月）。

    字段与平台结算页一一对应，均为平台真实数值：
        income            当月收益（元）
        available_income  累计可结算收益（元）
        total_diamond     累计消耗钻石
        sharable_flow     可分成钻石流水
        developer_share   开发者分成（钻石）
        incentive_income  鼓励金额（元）
        pay_punish_fee    罚款金额（元）
        play_plan_income  畅玩计划收益（元）
        total_usage_price 网络服估计用量成本（元）
        tax               税费（元）
        tech_service_fee  技术服务费（元，新版已取消恒为 0）
    """

    data_month: str = ""
    platform: str = ""
    income: float = 0.0
    available_income: float = 0.0
    total_diamond: int = 0
    sharable_flow: float = 0.0
    developer_share: float = 0.0
    incentive_income: float = 0.0
    pay_punish_fee: float = 0.0
    play_plan_income: float = 0.0
    total_usage_price: float = 0.0
    tax: float = 0.0
    tech_service_fee: float = 0.0
    exchange_rate: float = 0.01
    settle_status: int = 0
    type: str = ""
    op_time: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def share_rmb(self) -> float:
        """开发者分成折算人民币（元）。"""
        return round(self.developer_share * (self.exchange_rate or 0.01), 2)

    @property
    def ecosystem_cost(self) -> int:
        """被分摊的生态成本（钻石）= 累计消耗 − 可分成流水。"""
        return max(int(round(self.total_diamond - self.sharable_flow)), 0)

    @property
    def ecosystem_cost_rate(self) -> float:
        """由结算数据反推的生态成本分摊比例（0~1）。"""
        if self.total_diamond <= 0:
            return 0.0
        return round(self.ecosystem_cost / self.total_diamond, 4)

    @property
    def share_ratio(self) -> float:
        """由结算数据反推的分成比例。"""
        if self.sharable_flow <= 0:
            return 0.0
        return round(self.developer_share / self.sharable_flow, 4)

    @property
    def settled(self) -> bool:
        return bool(self.op_time) or self.income > 0

    @classmethod
    def parse(cls, obj: dict) -> "Settlement":
        def money(key: str) -> float:
            try:
                return round(float(obj.get(key) or 0), 2)
            except (TypeError, ValueError):
                return 0.0

        def num(key: str) -> float:
            try:
                return float(obj.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        return cls(
            data_month=str(obj.get("data_month") or ""),
            platform=str(obj.get("platform") or ""),
            income=money("income"),
            available_income=money("available_income"),
            total_diamond=_to_int(obj.get("total_diamond")),
            sharable_flow=round(num("sharable_flow"), 2),
            developer_share=round(num("developer_share"), 2),
            incentive_income=money("incentive_income"),
            pay_punish_fee=money("pay_punish_fee"),
            play_plan_income=money("play_plan_income"),
            total_usage_price=money("total_usage_price"),
            tax=money("tax"),
            tech_service_fee=money("tech_service_fee"),
            exchange_rate=num("exchange_rate") or 0.01,
            settle_status=_to_int(obj.get("settle_status")),
            type=str(obj.get("type") or ""),
            op_time=str(obj.get("op_time") or ""),
            raw=obj,
        )


@dataclass
class MonthRevenue:
    """某个月的收益汇总（含按最新分成规则推算的实际收益）。"""

    monthid: str
    total_diamond: int = 0
    developer_share: int = 0     # 开发者分成（钻石，按规则推算）
    share_rmb: float = 0.0       # 开发者分成（人民币，元）
    incentive_rmb: float = 0.0   # 鼓励金额（人民币，元）
    share_ratio: float = 0.5     # 该月适用的分成比例
    sharable: int = 0            # 可分成钻石流水
    sales: int = 0
    days: int = 0
    maps: List[MapRevenue] = field(default_factory=list)

    @property
    def ratio_percent(self) -> str:
        return f"{self.share_ratio * 100:.1f}%"

    @property
    def income_rmb(self) -> float:
        """预计当月收益（元）= 开发者分成 + 鼓励金额。"""
        return round(self.share_rmb + self.incentive_rmb, 2)

    @property
    def daily_avg_diamond(self) -> float:
        return round(self.total_diamond / self.days, 2) if self.days else 0.0

    @property
    def daily_avg_sales(self) -> float:
        return round(self.sales / self.days, 2) if self.days else 0.0


__all__ = [
    "DailyRow",
    "MonthlyRow",
    "ItemSummary",
    "MapRevenue",
    "MonthRevenue",
    "Settlement",
]
