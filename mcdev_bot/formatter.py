"""消息渲染：把统计数据排版成适合 QQ 阅读的文本。

说明：我的世界中国版钻石与人民币的兑换比例约为 1 元 = 100 钻石，
因此这里同时给出钻石数与折算人民币，方便直观理解收益规模。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from .models import DailyRow, MapRevenue, MonthRevenue, Settlement
from .revenue import PartnerShare, tier_label
from .service import Overview

DIAMOND_PER_YUAN = 100  # 1 元 ≈ 100 钻石

PLATFORM_LABEL = {
    "pe": "手机版组件",
    "pc": "电脑版组件",
    "jpe": "手机版联机",
    "jpc": "电脑版联机",
    "adv": "广告投放",
    "lobby": "联机大厅",
}

# 开发者昵称（插件运行时写入，用于消息署名与图表 logo）
_developer_name: str = ""

HELP_TEXT = """我的世界开发者收益助手 · 使用说明

【文字查询】
· 收益 / 总览 [天数]     最近 N 天总览（默认 7 天）
· 地图 / 地图收益 [天数]  各地图（作品）钻石收益与销量排行
· 昨日                   昨日钻石收益与销量
· 日均 [天数]            日均钻石收益与销量
· 月报 [月数]            各月钻石收益（默认 6 个月）
· 趋势 [天数]            最近 N 天每日收益明细
· 分成 [月数]            官方结算（真实）+ 团队贡献值分成 + 规则推算（参考）
· 结算                   查看平台官方结算单（当月收益/鼓励/税费等真实数值）
· 余额 / 钱包            账户余额：我的收益 / 未提取收益 / 结算方式 / 收款账户
· 反馈                   玩家反馈列表（内容 / 时间 / 处理状态）
· 退款反馈               玩家退款反馈（退款账单明细）
· 退款账单 [天数]        所有退款账单 + 退款率
· 数据 / 运营 [天数]     日活 / 组件涨粉 / 人均游玩时长 / 退款率
· 活动                   作品活动：模组征集 / 折扣特卖
· 新活动                 检查是否有新的模组征集活动
· 秒杀                   可参与周末秒杀的日期与名额
· 秒杀记录               我的秒杀申请记录
· 秒杀申请 日期 作品ID   提交周末秒杀申请（仅群主/管理员）
· 作品ID                 列出账号内作品的 ID（发给群成员用）
· 成员                   查看本群成员及 QQ 号（标出团队成员）
· 推送测试 [目标]        立即执行一次推送，预览推送效果
· 状态                   检查开发者平台登录状态
· 帮助                   显示本说明

【图表推送（返回图片）】
· 图表 / 收益图 [天数]    收益看板：地图排行 + 每日趋势（默认 14 天）
· 排行图 [天数]          各地图钻石收益排行图（默认 7 天）
· 趋势图 [天数]          每日收益趋势折线图（默认 14 天）
· 月报图 [月数]          各月收益柱状图（默认 6 个月）

【示例】
· 收益 30
· 地图 7
· 图表 14
· 月报图 12

提示：钻石与人民币约 1 元 = 100 钻石。"""


def fmt_int(value) -> str:
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "0"


def fmt_yuan(diamond) -> str:
    try:
        return f"{float(diamond) / DIAMOND_PER_YUAN:,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def fmt_float(value, digits: int = 2) -> str:
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "0"


def fmt_diamond(diamond) -> str:
    """钻石 + 折算人民币。"""
    return f"{fmt_int(diamond)} 钻石（≈ {fmt_yuan(diamond)} 元）"


def _platform_title() -> str:
    from .config import settings

    label = PLATFORM_LABEL.get(settings.platform, settings.platform)
    extra = f"｜筛选：{settings.item_keyword}" if settings.item_keyword else ""
    dev = f"{_developer_name}｜" if _developer_name else ""
    return f"【{dev}{label}{extra}】"


def set_developer_name(name: str) -> None:
    """由插件在启动/首次查询时写入开发者昵称。"""
    global _developer_name
    _developer_name = (name or "").strip()


def get_developer_name() -> str:
    return _developer_name


def _source_note() -> str:
    from .config import settings

    return "\n数据来源：演示数据（未配置 Cookie）" if settings.use_mock else ""


def _range_text(start: str, end: str) -> str:
    if start == end:
        return start
    return f"{start} ~ {end}"


def _clip(text, limit: int) -> str:
    """截断过长文本，超出部分以省略号结尾。"""
    s = str(text or "").strip().replace("\n", " ")
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: max(limit - 1, 0)] + "…"


def _fmt_day(value) -> str:
    """把 YYYYMMDD 或 ISO 时间统一成 YYYY-MM-DD。"""
    s = str(value or "").strip()
    if len(s) >= 10 and s[4] == "-":
        return s[:10]
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def render_overview(ov: Overview, days: int) -> str:
    lines = [
        "我的世界开发者收益 · 总览",
        _platform_title(),
        f"统计区间：{_range_text(ov.start_date, ov.end_date)}（{ov.days} 天）",
        "",
        f"钻石收益：{fmt_diamond(ov.total_diamond)}",
        f"销量合计：{fmt_int(ov.total_sales)} 份",
        f"下载量合计：{fmt_int(ov.total_download)} 次",
        f"日均收益：{fmt_diamond(ov.daily_avg_diamond)}",
        f"日均销量：{fmt_float(ov.daily_avg_sales)} 份",
    ]
    if ov.maps:
        lines.append("")
        lines.append(f"作品数量：{len(ov.maps)} 个")
        lines.append(f"最畅销：{ov.maps[0].name}")
    lines.append(_source_note())
    return "\n".join(lines)


def render_maps(ov: Overview, top_n: int = 10) -> str:
    header = [
        "我的世界开发者收益 · 各地图排行",
        _platform_title(),
        f"统计区间：{_range_text(ov.start_date, ov.end_date)}（{ov.days} 天）",
        "",
    ]
    if not ov.maps:
        header.append("该区间暂无可统计的地图 / 作品数据。")
        return "\n".join(header) + _source_note()

    lines = header
    for idx, item in enumerate(ov.maps[:top_n], start=1):
        lines.append(
            f"{idx}. {item.name}\n"
            f"   钻石收益：{fmt_int(item.diamond)}（≈ {fmt_yuan(item.diamond)} 元）\n"
            f"   销量：{fmt_int(item.sales)} 份｜日均收益：{fmt_int(item.daily_avg_diamond)} 钻石"
        )
    if len(ov.maps) > top_n:
        lines.append(f"\n…… 其余 {len(ov.maps) - top_n} 个作品已省略")
    lines.append(
        f"\n合计：{fmt_diamond(ov.total_diamond)}｜销量 {fmt_int(ov.total_sales)} 份"
    )
    lines.append(_source_note())
    return "\n".join(lines)


def render_yesterday(ov: Overview, title: str = "我的世界开发者收益 · 昨日") -> str:
    lines = [
        title,
        _platform_title(),
        f"日期：{ov.end_date}",
        "",
        f"钻石收益：{fmt_diamond(ov.total_diamond)}",
        f"销量：{fmt_int(ov.total_sales)} 份",
        f"下载量：{fmt_int(ov.total_download)} 次",
    ]
    if ov.maps:
        lines.append("")
        lines.append("各地图明细：")
        for idx, item in enumerate(ov.maps[:10], start=1):
            lines.append(
                f"{idx}. {item.name}：{fmt_int(item.diamond)} 钻石 / {fmt_int(item.sales)} 份"
            )
    lines.append(_source_note())
    return "\n".join(lines)


def render_daily_average(ov: Overview, days: int) -> str:
    lines = [
        "我的世界开发者收益 · 日均",
        _platform_title(),
        f"统计区间：{_range_text(ov.start_date, ov.end_date)}（{ov.days} 天）",
        "",
        f"日均钻石收益：{fmt_diamond(ov.daily_avg_diamond)}",
        f"日均销量：{fmt_float(ov.daily_avg_sales)} 份",
        f"区间总收益：{fmt_diamond(ov.total_diamond)}",
    ]
    if ov.maps:
        lines.append("")
        lines.append("各地图日均收益：")
        for idx, item in enumerate(ov.maps[:10], start=1):
            lines.append(
                f"{idx}. {item.name}：{fmt_int(item.daily_avg_diamond)} 钻石/天"
                f"（{fmt_int(item.daily_avg_sales)} 份/天）"
            )
    lines.append(_source_note())
    return "\n".join(lines)


def render_monthly(months: List[MonthRevenue], top_n: int = 5) -> str:
    lines = [
        "我的世界开发者收益 · 月报",
        _platform_title(),
        "",
    ]
    if not months:
        lines.append("暂无月度收益数据。")
        return "\n".join(lines) + _source_note()

    for month in months:
        label = month.monthid
        if len(label) == 6:
            label = f"{label[:4]}-{label[4:]}"
        lines.append(
            f"{label}（{month.days} 天）\n"
            f"   钻石收益：{fmt_int(month.total_diamond)}（≈ {fmt_yuan(month.total_diamond)} 元）\n"
            f"   销量：{fmt_int(month.sales)} 份｜日均：{fmt_int(month.daily_avg_diamond)} 钻石/天"
        )
        for idx, item in enumerate(month.maps[:top_n], start=1):
            lines.append(f"      · {item.name}：{fmt_int(item.diamond)} 钻石")
    lines.append(_source_note())
    return "\n".join(lines)


def render_trend(rows: Iterable[DailyRow], days: int) -> str:
    rows = list(rows)
    lines = [
        "我的世界开发者收益 · 每日趋势",
        _platform_title(),
        f"最近 {days} 天",
        "",
    ]
    if not rows:
        lines.append("暂无数据。")
        return "\n".join(lines) + _source_note()
    for row in rows:
        label = row.dateid
        if len(label) == 8:
            label = f"{label[:4]}-{label[4:6]}-{label[6:]}"
        lines.append(
            f"{label}：{fmt_int(row.diamond)} 钻石（≈ {fmt_yuan(row.diamond)} 元）"
            f"｜{fmt_int(row.cnt_buy)} 份"
        )
    lines.append(_source_note())
    return "\n".join(lines)


def render_status(
    logged_in: bool,
    user: Optional[dict] = None,
    error: str = "",
    official: Optional[dict] = None,
) -> str:
    from .config import settings

    lines = ["我的世界开发者平台 · 登录状态", ""]
    if settings.use_mock:
        lines.append("当前为【演示模式】：未配置 MCDEV_COOKIE，展示的是示例数据。")
        lines.append("在 .env 中填入真实 Cookie 后重启即可读取你自己的收益。")
        return "\n".join(lines)
    if logged_in:
        name = (user or {}).get("nickname") or (user or {}).get("nick_name") or "未知"
        lines.append("登录状态：正常")
        lines.append(f"开发者：{name}")
        lines.append(f"接口基址：{settings.base_url}")
        lines.append(f"统计平台：{PLATFORM_LABEL.get(settings.platform, settings.platform)}")
        if official:
            lines.append("")
            lines.append("平台官方口径（overview 接口）：")
            lines.append(f"   昨日钻石：{fmt_int(official.get('yesterday_diamond', 0))}")
            lines.append(f"   近 14 天合计：{fmt_int(official.get('days_14_total_diamond', 0))}")
            lines.append(f"   近 14 天日均：{fmt_int(official.get('days_14_average_diamond', 0))}")
            lines.append(f"   本月钻石：{fmt_int(official.get('this_month_diamond', 0))}")
            lines.append(f"   上月钻石：{fmt_int(official.get('last_month_diamond', 0))}")
    else:
        lines.append("登录状态：异常")
        if error:
            lines.append(f"原因：{error}")
        lines.append("请重新登录开发者平台并更新 .env 中的 MCDEV_COOKIE。")
    return "\n".join(lines)


def render_income(
    months: List[MonthRevenue],
    ecosystem_rate: float = 0.0,
    top_n: int = 3,
) -> str:
    """按 2026 新版《开发者协议》推算各月实际收益（人民币）。

    计算公式：钻石流水 −(生态成本)→ 可分成流水 ×阶梯比例 = 开发者分成（钻石）
             → 折算人民币 +鼓励金额 = 当月收益
    """
    lines = [
        "我的世界开发者收益 · 规则推算（参考）",
        _platform_title(),
        "规则：2026 新版《开发者协议》｜单作品独立核算 · 阶梯递增 · 无技术服务费",
    ]
    if ecosystem_rate:
        lines.append(f"生态成本分摊：{ecosystem_rate * 100:.2f}%（已按官方结算校准）")
    lines.append("")
    if not months:
        lines.append("暂无月度收益数据。")
        return "\n".join(lines) + _source_note()

    total_income = 0.0
    for month in months:
        label = month.monthid
        if len(label) == 6:
            label = f"{label[:4]}-{label[4:]}"
        total_income += month.income_rmb
        lines.append(
            f"{label}（{month.days} 天）\n"
            f"   钻石流水：{fmt_int(month.total_diamond)}\n"
            f"   可分成流水：{fmt_int(month.sharable)}（{tier_label(month.total_diamond)}）\n"
            f"   分成比例：{month.ratio_percent}\n"
            f"   开发者分成：{fmt_int(month.developer_share)} 钻石 ≈ {fmt_float(month.share_rmb)} 元"
        )
        if month.incentive_rmb:
            lines.append(
                f"   鼓励金额：{fmt_float(month.incentive_rmb)} 元\n"
                f"   预计当月收益：{fmt_float(month.income_rmb)} 元"
            )
        for item in month.maps[:top_n]:
            lines.append(f"      · {item.name}：{fmt_int(item.diamond)} 钻石")

    lines.append("")
    lines.append(f"合计（{len(months)} 个月）：≈ {fmt_float(total_income)} 元")
    lines.append("")
    lines.append("注：按公开规则推算；实际以平台官方结算为准。")
    lines.append(_source_note())
    return "\n".join(lines)


def render_income_summary(summary: dict, title: str = "我的世界开发者收益 · 预计实际收益") -> str:
    """展示「官方已结算 + 未结算预估」的合计实际收益。"""
    settled = float(summary.get("settled_rmb") or 0.0)
    pending = float(summary.get("pending_rmb") or 0.0)
    total = float(summary.get("total_rmb") or 0.0)
    eco = float(summary.get("eco_rate") or 0.0)
    settled_months = summary.get("settled_months") or []
    pending_months = summary.get("pending_months") or []

    lines = [title, _platform_title(), ""]
    lines.append(f"官方已结算：{fmt_float(settled)} 元")
    if settled_months:
        lines.append(f"   已结算月份：{'、'.join(settled_months)}")
    lines.append(f"未结算预估：{fmt_float(pending)} 元")
    if pending_months:
        lines.append(f"   未结算月份：{'、'.join(pending_months)}")
    if eco:
        lines.append(f"   预估口径：生态成本 {eco * 100:.2f}% + 阶梯分成")
    lines.append("")
    lines.append(f"预计实际收益合计：{fmt_float(total)} 元")
    return "\n".join(lines)


def partner_lines(shares: List[PartnerShare]) -> List[str]:
    """生成每位成员的分成文案（不含 @，@ 由插件按 QQ 号拼接）。"""
    result = []
    for share in shares:
        result.append(
            f"{share.partner.name}（{share.partner.percent:g}%）："
            f"{fmt_int(share.diamonds)} 钻石 ≈ {fmt_float(share.rmb)} 元"
        )
    return result


def render_settlement(records: List[Settlement], title: str = "我的世界开发者收益 · 官方结算") -> str:
    """展示平台官方结算记录（真实数值，与开发者平台「收益结算」页一致）。"""
    lines = [
        title,
        _platform_title(),
        "数据来源：开发者平台「收益结算」，为平台真实结算值",
        "",
    ]
    if not records:
        lines.append("暂无官方结算记录（平台通常于次月 10 日左右出账）。")
        return "\n".join(lines)

    total_income = 0.0
    for rec in records:
        total_income += rec.income
        label = rec.data_month or "未知月份"
        lines.append(
            f"{label}（{PLATFORM_LABEL.get(rec.platform, rec.platform)}）\n"
            f"   当月收益：{fmt_float(rec.income)} 元\n"
            f"   累计可结算收益：{fmt_float(rec.available_income)} 元\n"
            f"   累计消耗钻石：{fmt_int(rec.total_diamond)}\n"
            f"   可分成流水：{fmt_float(rec.sharable_flow)}"
            f"（生态成本 {fmt_int(rec.ecosystem_cost)}，约 {rec.ecosystem_cost_rate * 100:.2f}%）\n"
            f"   开发者分成：{fmt_float(rec.developer_share)} 钻石"
            f" ≈ {fmt_float(rec.share_rmb)} 元（比例 {rec.share_ratio * 100:.1f}%）\n"
            f"   鼓励金额：{fmt_float(rec.incentive_income)} 元\n"
            f"   罚款金额：{fmt_float(rec.pay_punish_fee)} 元\n"
            f"   畅玩计划收益：{fmt_float(rec.play_plan_income)} 元\n"
            f"   网络服估计用量成本：{fmt_float(rec.total_usage_price)} 元\n"
            f"   税费：{fmt_float(rec.tax)} 元"
        )

    lines.append("")
    lines.append(f"累计已结算收益：{fmt_float(total_income)} 元")
    return "\n".join(lines)


# 结算状态文案（取自开发者平台前端 renderStatus 映射）
SETTLE_STATUS_LABEL = {
    "init": "未结算",
    "preparing": "准备发票中",
    "fail": "结算失败",
    "applying": "结算中",
    "pay_success": "已打款",
    "pay_fail": "打款失败",
}

# 结算方式文案（取自开发者平台前端 billType 映射）
PAY_TYPE_LABEL = {
    "individual_withhold": "个人开发者代扣代缴",
    "individual_owned": "个人开发者自备税票",
    "company_owned": "公司开发者自备税票",
}


def render_balance(
    data: Dict[str, object],
    title: str = "我的世界开发者收益 · 账户余额",
) -> str:
    """账户余额（平台 ``users/me`` 口径，真实数值）。"""

    def rmb(key: str) -> str:
        try:
            return f"{float(data.get(key) or 0):,.2f}"
        except (TypeError, ValueError):
            return "0.00"

    def num(key: str) -> int:
        try:
            return int(data.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    lines = [
        title,
        _platform_title(),
        "",
        f"我的收益：￥{rmb('income_rmb')} 元",
        f"未提取收益：￥{rmb('unextract_rmb')} 元",
    ]

    pay_type = str(data.get("pay_type") or "")
    pay_label = PAY_TYPE_LABEL.get(pay_type, pay_type)
    if pay_label:
        lines.append(f"结算方式：{pay_label}")

    bank = str(data.get("bank") or "")
    card_no = str(data.get("card_no") or "")
    if bank or card_no:
        lines.append(f"收款账户：{bank}　{card_no}".rstrip())

    deposit = rmb("deposit")
    incentive = rmb("incentive_fund")
    if float(str(data.get("deposit") or 0) or 0) > 0:
        lines.append(f"保证金：￥{deposit} 元")
    if float(str(data.get("incentive_fund") or 0) or 0) > 0:
        lines.append(f"当月鼓励金：￥{incentive} 元")

    lines.append("")

    last_month = str(data.get("last_month") or "")
    if last_month:
        status = str(data.get("last_status") or "")
        status_label = SETTLE_STATUS_LABEL.get(status, status)
        line = f"最近出账：{last_month}　￥{rmb('last_income')} 元"
        if status_label:
            line += f"（{status_label}）"
        lines.append(line)
        lines.append(
            f"结算单累计：￥{rmb('settled_rmb')} 元（{num('settled_count')} 个月）"
        )
    else:
        lines.append("暂无官方结算记录（平台通常于次月 10 日左右出账）。")

    total_diamond = num("total_diamond")
    if total_diamond:
        lines.append(f"累计消耗钻石：{fmt_int(total_diamond)}")

    lines.append("")
    lines.append("「我的收益 / 未提取收益」取自开发者平台账号信息，为平台真实数值")
    return "\n".join(lines)


# 玩家反馈状态文案
FEEDBACK_STATUS_LABEL = {
    0: "待处理",
    1: "已回复",
    2: "已关闭",
    "0": "待处理",
    "1": "已回复",
    "2": "已关闭",
}

# 秒杀申请状态文案（取自开发者平台前端 flashsaleStatus）
FLASHSALE_STATUS_LABEL = {
    0: "审核中",
    1: "已通过",
    2: "未通过",
    3: "取消申请",
    4: "已下架",
    5: "已上架",
}


def render_feedback(items: List[Dict[str, object]], top_n: int = 8) -> str:
    """玩家反馈列表。"""
    lines = [
        "我的世界开发者收益 · 玩家反馈",
        _platform_title(),
        "",
    ]
    if not items:
        lines.append("暂无玩家反馈。")
        return "\n".join(lines)

    lines.append(f"共 {len(items)} 条，最近 {min(top_n, len(items))} 条：")
    for it in items[:top_n]:
        status = it.get("status")
        label = FEEDBACK_STATUS_LABEL.get(status, str(status) if status is not None else "")
        head = f"· {it.get('item_name') or '未知作品'}"
        if label:
            head += f"［{label}］"
        lines.append(head)
        content = str(it.get("content") or "").strip()
        if content:
            lines.append(f"  {_clip(content, 60)}")
        when = str(it.get("create_time") or "")
        if when:
            lines.append(f"  时间：{when}")
    return "\n".join(lines)


def render_refund(
    data: Dict[str, object],
    top_n: int = 10,
    title: str = "我的世界开发者收益 · 退款账单",
) -> str:
    """退款账单 + 退款率。"""
    count = int(data.get("count") or 0)
    sold = int(data.get("sold") or 0)
    rate = data.get("rate")

    lines = [
        title,
        _platform_title(),
        "",
        f"退款笔数：{fmt_int(count)}",
        f"同期成交：{fmt_int(sold)} 笔",
    ]
    if rate is None:
        lines.append("退款率：—（缺成交数据）")
    else:
        lines.append(f"退款率：{fmt_float(rate)}%")

    by_item = data.get("by_item") or []
    if by_item:
        lines.append("")
        lines.append("按作品：")
        for name, n in list(by_item)[:top_n]:
            lines.append(f"· {_clip(str(name), 22)}：{fmt_int(n)} 笔")

    bills = data.get("bills") or []
    if bills:
        lines.append("")
        lines.append(f"最近 {min(top_n, len(bills))} 条明细：")
        for b in bills[:top_n]:
            when = _fmt_day(str(b.get("refund_time") or ""))
            reason = str(b.get("reason") or "未填")
            lines.append(
                f"· {when}　{_clip(str(b.get('item_name') or ''), 16)}\n"
                f"  原因：{_clip(reason, 40)}"
            )
    else:
        lines.append("")
        lines.append("暂无退款记录。")
    return "\n".join(lines)


def render_analytics(data: Dict[str, object], top_n: int = 6) -> str:
    """运营数据：日活 / 组件涨粉 / 人均游玩时长 / 退款率。"""
    lines = [
        "我的世界开发者收益 · 运营数据",
        _platform_title(),
        f"统计区间：{data.get('start_date')} ~ {data.get('end_date')}"
        f"（{data.get('days')} 天）",
        "",
        f"日均日活：{fmt_float(data.get('dau_avg'), 1)}",
        f"组件涨粉：{fmt_int(data.get('focus_total'))}",
        f"人均游玩时长：{fmt_float(data.get('play_avg'), 1)} 分钟",
        f"退款率：{fmt_float(data.get('refund_rate'))}%",
    ]

    items = data.get("items") or []
    if items:
        lines.append("")
        lines.append("按作品（日均日活排序）：")
        for it in items[:top_n]:
            lines.append(
                f"· {_clip(str(it.get('name') or ''), 20)}\n"
                f"  日均日活 {fmt_float(it.get('dau_avg'), 1)}　"
                f"涨粉 {fmt_int(it.get('focus'))}　"
                f"时长 {fmt_float(it.get('play_avg'), 1)} 分　"
                f"退款率 {fmt_float(it.get('refund_rate'))}%"
            )
    return "\n".join(lines)


def render_activities(data: Dict[str, object], top_n: int = 5) -> str:
    """作品活动 / 折扣特卖 / 模组征集。"""
    lines = ["我的世界开发者收益 · 活动中心", _platform_title(), ""]

    active = data.get("active")
    review = data.get("review") or []
    shown = active if active is not None else review

    lines.append(f"进行中／待开始活动：{len(shown)} 个（历史累计 {len(review)} 个）")
    if shown:
        for a in shown[:top_n]:
            lines.append(f"· {a.get('name') or '未命名活动'}")
            if a.get("apply_end_at"):
                lines.append(f"  报名截止：{a.get('apply_end_at')}")
            if a.get("begin_at") or a.get("end_at"):
                lines.append(f"  活动时间：{a.get('begin_at')} ~ {a.get('end_at')}")
            desc = str(a.get("desc") or "").strip()
            if desc:
                lines.append(f"  {_clip(desc, 100)}")
    else:
        lines.append("（暂无进行中的征集活动）")

    discount = data.get("discount") or {}
    lines.append("")
    if discount:
        lines.append(f"折扣特卖：{discount.get('name') or '进行中'}")
        if discount.get("begin_at") or discount.get("end_at"):
            lines.append(f"  活动时间：{discount.get('begin_at')} ~ {discount.get('end_at')}")
        instr = str(discount.get("instruction") or "").strip()
        desc = str(discount.get("desc") or "").strip()
        text = instr if len(instr) > len(desc) else desc
        if text and text != "/":
            lines.append(f"  {_clip(text, 150)}")
    else:
        lines.append("折扣特卖：暂无进行中的活动")
    return "\n".join(lines)


def render_flashsale(data: Dict[str, object], top_n: int = 12) -> str:
    """可参与周末秒杀的日期。"""
    lines = [
        "我的世界开发者收益 · 周末秒杀可申请日期",
        _platform_title(),
        f"今天：{data.get('today')}　可申请窗口：{data.get('window')}",
        f"每日名额上限：{fmt_int(data.get('quota'))}",
        "",
    ]
    dates = data.get("dates") or []
    if not dates:
        lines.append("当前窗口内暂无可申请日期。")
        return "\n".join(lines)

    for d in dates[:top_n]:
        tag = "已满" if d.get("full") else f"剩余 {fmt_int(d.get('left'))}"
        lines.append(f"· {d.get('label')}　已用 {fmt_int(d.get('used'))}／{tag}")
    lines.append("")
    lines.append("申请方式：管理员/群主发送「秒杀申请 日期 模组ID」")
    return "\n".join(lines)


def render_flashsale_history(items: List[Dict[str, object]], top_n: int = 10) -> str:
    """秒杀申请历史。"""
    lines = ["我的世界开发者收益 · 秒杀申请记录", _platform_title(), ""]
    if not items:
        lines.append("暂无秒杀申请记录。")
        return "\n".join(lines)
    for it in items[:top_n]:
        st = it.get("status")
        label = FLASHSALE_STATUS_LABEL.get(st, str(st) if st is not None else "")
        when = _fmt_day(str(it.get("date") or ""))
        lines.append(f"· {when}　{_clip(str(it.get('item_name') or ''), 18)}")
        lines.append(
            f"  限量 {fmt_int(it.get('num'))}　单价 {fmt_int(it.get('price'))} 钻石"
            f"　［{label}］"
        )
    return "\n".join(lines)


__all__ = [
    "HELP_TEXT",
    "fmt_int",
    "fmt_yuan",
    "fmt_float",
    "fmt_diamond",
    "set_developer_name",
    "get_developer_name",
    "render_overview",
    "render_maps",
    "render_yesterday",
    "render_daily_average",
    "render_monthly",
    "render_trend",
    "render_status",
    "render_income",
    "render_income_summary",
    "render_settlement",
    "render_balance",
    "render_feedback",
    "render_refund",
    "render_analytics",
    "render_activities",
    "render_flashsale",
    "render_flashsale_history",
    "partner_lines",
]
