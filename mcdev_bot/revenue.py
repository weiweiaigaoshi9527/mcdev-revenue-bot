"""我的世界（中国版）开发者分成规则与收益换算。

▍规则来源（2026-01-01 生效的新版《开发者协议》）
    · 官方 FAQ：https://mc.163.com/m/dev/developer_cn/news/update/20251223/37048_1278098.html
    · 分成重构公告：https://www.bilibili.com/opus/1149517811763118085

▍核心变化（相较旧版）
    · 计算依据由「开发者账号总流水」改为「单个作品月钻石流水」，每个作品独立核算
    · 阶梯由「递减」改为「递增」：流水越高，分成比例越高
    · 取消「技术服务费」（旧版高流水作品最高被抽 30%）

▍计算公式
    开发者收益 = 单作品可分成钻石流水 × 分成比例 + 专项补贴 − 违约金

    其中「可分成钻石流水」= 作品当月钻石流水 − 需分摊的生态成本
    （生态成本比例平台未公开，本项目用 MCDEV_ECOSYSTEM_COST_RATE 配置，默认 0 即不扣减）

▍阶梯比例（按单个作品的自然月钻石流水）
    < 100 万钻石          -> 50%
    100 万 ~ 1000 万钻石   -> 52.5%
    >= 1000 万钻石         -> 55%

▍货币换算
    钻石 : 人民币 ≈ 100 : 1（100 钻石 = 1 元）

⚠ 说明：本模块是「按公开规则推算」，实际到账金额还会受生态成本分摊、平台奖励、
   税费代扣等因素影响，与平台结算页可能存在差异。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# 钻石兑人民币：100 钻石 = 1 元
DIAMOND_PER_YUAN = 100

# 阶梯表：(该档流水下限, 分成比例)，按下限从高到低排列
SHARE_TIERS: Tuple[Tuple[int, float], ...] = (
    (10_000_000, 0.55),
    (1_000_000, 0.525),
    (0, 0.50),
)


def share_ratio(monthly_diamond: int) -> float:
    """按单个作品月钻石流水取对应的分成比例。"""
    value = int(monthly_diamond or 0)
    for threshold, ratio in SHARE_TIERS:
        if value >= threshold:
            return ratio
    return 0.50


def tier_label(monthly_diamond: int) -> str:
    """返回该流水所处的档位描述，用于展示。"""
    value = int(monthly_diamond or 0)
    if value >= 10_000_000:
        return "≥1000万档"
    if value >= 1_000_000:
        return "100万~1000万档"
    return "<100万档"


def sharable_flow(monthly_diamond: int, ecosystem_cost_rate: float = 0.0) -> int:
    """可分成钻石流水 = 月钻石流水 − 需分摊的生态成本。"""
    rate = min(max(float(ecosystem_cost_rate or 0.0), 0.0), 1.0)
    return int(round(int(monthly_diamond or 0) * (1.0 - rate)))


def developer_share(sharable: int, ratio: Optional[float] = None) -> int:
    """开发者分成（钻石）。未传比例时按可分成流水自动取档。"""
    if ratio is None:
        ratio = share_ratio(sharable)
    return int(round(int(sharable or 0) * float(ratio)))


def diamonds_to_rmb(diamonds) -> float:
    """钻石换算人民币（元）。"""
    try:
        return round(float(diamonds or 0) / DIAMOND_PER_YUAN, 2)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class IncomeBreakdown:
    """单个作品（或整月合计）的收益拆解。"""

    monthly_diamond: int = 0        # 当月钻石流水
    ecosystem_cost: int = 0         # 分摊的生态成本
    sharable: int = 0               # 可分成钻石流水
    ratio: float = 0.5              # 分成比例
    share_diamonds: int = 0         # 开发者分成（钻石）
    share_rmb: float = 0.0          # 开发者分成（人民币）
    incentive_rmb: float = 0.0      # 鼓励金额（人民币）

    @property
    def ratio_percent(self) -> str:
        """比例展示，例如 52.5%。"""
        return f"{self.ratio * 100:.1f}%"

    @property
    def tier(self) -> str:
        return tier_label(self.monthly_diamond)

    @property
    def income_rmb(self) -> float:
        """预计当月收益（元）= 开发者分成 + 鼓励金额。"""
        return round(self.share_rmb + self.incentive_rmb, 2)


def build_breakdown(
    monthly_diamond: int,
    ecosystem_cost_rate: float = 0.0,
    extra_diamonds: int = 0,
    incentive_rate: float = 0.0,
) -> IncomeBreakdown:
    """按最新规则计算一个作品的收益拆解。

    :param monthly_diamond: 作品当月钻石流水
    :param ecosystem_cost_rate: 生态成本分摊比例（0~1），可由官方结算反推校准
    :param extra_diamonds: 额外收益（平台奖励 / 订阅 / 广告等，单位钻石）
    :param incentive_rate: 鼓励金额比例（鼓励金额 = 开发者分成 × 该比例）
    """
    flow = int(monthly_diamond or 0)
    sharable = sharable_flow(flow, ecosystem_cost_rate)
    ratio = share_ratio(sharable)
    share = developer_share(sharable, ratio) + int(extra_diamonds or 0)
    share_rmb = diamonds_to_rmb(share)
    incentive = round(share_rmb * float(incentive_rate or 0.0), 2)
    return IncomeBreakdown(
        monthly_diamond=flow,
        ecosystem_cost=flow - sharable,
        sharable=sharable,
        ratio=ratio,
        share_diamonds=share,
        share_rmb=share_rmb,
        incentive_rmb=incentive,
    )


# ----------------------------------------------------------------------
# 贡献值（团队成员）分成
# ----------------------------------------------------------------------
@dataclass
class Partner:
    """一位收益分成成员。"""

    name: str
    percent: float          # 贡献值占比（0~100）
    qq: str = ""            # 用于 @ 的 QQ 号，留空则只显示名字

    @property
    def is_valid(self) -> bool:
        return bool(self.name) and self.percent > 0


@dataclass
class PartnerShare:
    """某位成员分到的金额。"""

    partner: Partner
    diamonds: int = 0
    rmb: float = 0.0


def split_among_partners(
    total_diamonds: int,
    partners: Sequence[Partner],
) -> List[PartnerShare]:
    """按贡献值把总收益（钻石）拆分给各位成员。

    采用「最后一个成员吃余数」的方式，保证各份之和精确等于总额。
    """
    valid = [p for p in partners if p.is_valid]
    if not valid:
        return []

    total_percent = sum(p.percent for p in valid)
    total = int(total_diamonds or 0)
    shares: List[PartnerShare] = []
    allocated = 0

    for index, partner in enumerate(valid):
        if index == len(valid) - 1:
            amount = total - allocated          # 余数归最后一位，避免累计误差
        else:
            amount = int(round(total * partner.percent / total_percent))
            allocated += amount
        shares.append(
            PartnerShare(
                partner=partner,
                diamonds=amount,
                rmb=diamonds_to_rmb(amount),
            )
        )
    return shares


def parse_partners(raw: str) -> List[Partner]:
    """解析 ``名字:占比:QQ`` 形式的配置，多项用逗号分隔。

    示例：``十方:10:123456,炜炜爱搞事:30:,hisuperwan:60:654321``
    QQ 可以留空（只显示名字，不 @）。
    """
    result: List[Partner] = []
    if not raw:
        return result
    for chunk in raw.replace("，", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split(":")]
        name = parts[0] if parts else ""
        if not name:
            continue
        try:
            percent = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
        except ValueError:
            percent = 0.0
        qq = parts[2] if len(parts) > 2 else ""
        partner = Partner(name=name, percent=percent, qq=qq)
        if partner.is_valid:
            result.append(partner)
    return result


__all__ = [
    "DIAMOND_PER_YUAN",
    "SHARE_TIERS",
    "share_ratio",
    "tier_label",
    "sharable_flow",
    "developer_share",
    "diamonds_to_rmb",
    "IncomeBreakdown",
    "build_breakdown",
    "Partner",
    "PartnerShare",
    "split_among_partners",
    "parse_partners",
]
