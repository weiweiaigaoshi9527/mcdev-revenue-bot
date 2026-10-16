"""平台无关的指令分发层。

把「指令文本 → 回复内容」的逻辑集中在这里，供不同接入端复用：
- 官方 QQ 机器人（``mcdev_bot/qqbot_bot.py``，qq-botpy）
- OneBot v11（``mcdev_bot/plugins/revenue/handler.py``，NoneBot/NapCat）

本模块不依赖任何机器人框架，只依赖业务层（service / formatter / chart）。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from . import chart
from .config import settings
from .formatter import (
    HELP_TEXT,
    fmt_int,
    partner_lines,
    render_activities,
    render_analytics,
    render_balance,
    render_daily_average,
    render_feedback,
    render_flashsale,
    render_flashsale_history,
    render_income,
    render_income_summary,
    render_maps,
    render_monthly,
    render_overview,
    render_refund,
    render_settlement,
    render_status,
    render_trend,
    render_yesterday,
    set_developer_name,
)
from .revenue import split_among_partners
from .service import RevenueService, build_client

# 官方群聊里不适合出现的指令（需要群成员列表 / 定时推送等）
QQ_HELP_EXTRA = """
【本机器人由官方 QQ 机器人接入，@机器人 即可使用】
"""

_service: Optional[RevenueService] = None


def get_service() -> RevenueService:
    global _service
    if _service is None:
        _service = RevenueService(build_client(settings), settings)
    return _service


def reset_service() -> None:
    global _service
    _service = None


@dataclass
class Reply:
    """一条回复：文字 + 可选图片。"""

    text: str = ""
    image: Optional[bytes] = None
    caption: str = ""
    files: List[str] = field(default_factory=list)


def _help_text() -> str:
    """帮助文本（官方机器人版：去掉 成员 / 推送测试）。"""
    lines = []
    for line in HELP_TEXT.splitlines():
        if "成员" in line and "查看本群成员" in line:
            continue
        if "推送测试" in line:
            continue
        lines.append(line)
    return "\n".join(lines) + QQ_HELP_EXTRA


def _parse_int(text: str, default: int, lo: int = 1, hi: int = 365) -> int:
    text = (text or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    return max(lo, min(hi, value))


async def _png(func, *args) -> bytes:
    """在线程池中渲染图表，避免阻塞事件循环。"""
    return await asyncio.to_thread(func, *args)


async def _charts_on() -> bool:
    return settings.chart_enabled and chart.charts_available()


def _chart_off_note() -> str:
    return "（图表未启用，以下为文字版）"


# ----------------------------------------------------------------------
# 各指令实现
# ----------------------------------------------------------------------
async def _cmd_overview(days: int) -> Reply:
    svc = get_service()
    ov = await svc.overview(days=days)
    return Reply(text=render_overview(ov, days))


async def _cmd_maps(days: int) -> Reply:
    svc = get_service()
    ov = await svc.per_map(days=days)
    return Reply(text=render_maps(ov, settings.chart_top_n))


async def _cmd_yesterday() -> Reply:
    svc = get_service()
    return Reply(text=render_yesterday(await svc.yesterday()))


async def _cmd_daily(days: int) -> Reply:
    svc = get_service()
    return Reply(text=render_daily_average(await svc.daily_average(days), days))


async def _cmd_monthly(months: int) -> Reply:
    svc = get_service()
    return Reply(text=render_monthly(await svc.monthly(months=months)))


async def _cmd_trend(days: int) -> Reply:
    svc = get_service()
    rows = await svc.recent_daily(days=days)
    return Reply(text=render_trend(rows, days))


async def _cmd_balance() -> Reply:
    svc = get_service()
    return Reply(text=render_balance(await svc.balance()))


async def _cmd_settlement() -> Reply:
    svc = get_service()
    return Reply(text=render_settlement(await svc.settlements()))


async def _cmd_feedback() -> Reply:
    svc = get_service()
    return Reply(text=render_feedback(await svc.feedback_list()))


async def _cmd_refund(days: int, title: str) -> Reply:
    svc = get_service()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    data = await svc.refund_bills(
        start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d")
    )
    return Reply(text=render_refund(data, title=title))


async def _cmd_analytics(days: int) -> Reply:
    svc = get_service()
    return Reply(text=render_analytics(await svc.analytics(days=days)))


async def _cmd_activities() -> Reply:
    svc = get_service()
    return Reply(text=render_activities(await svc.activities()))


async def _cmd_flashsale() -> Reply:
    svc = get_service()
    return Reply(text=render_flashsale(await svc.flashsale_dates()))


async def _cmd_flashsale_log() -> Reply:
    svc = get_service()
    return Reply(text=render_flashsale_history(await svc.flashsale_history()))


async def _cmd_items_id() -> Reply:
    svc = get_service()
    items = await svc.items()
    if not items:
        return Reply(text="账号下暂无作品。")
    lines = ["我的世界开发者收益 · 作品 ID 清单", ""]
    for it in items:
        tag = ""
        pt = str(it.price_type).lower()
        if pt == "diamond":
            tag = "　［钻石］" if int(it.price or 0) >= 100 else "　［钻石·不足100，不可秒杀］"
        elif it.price_type:
            tag = f"　［{it.price_type}］"
        lines.append(f"· {it.item_name}{tag}")
        lines.append(f"  ID：{it.item_id}")
    lines.append("")
    lines.append("申请秒杀：秒杀申请 日期 作品ID")
    return Reply(text="\n".join(lines))


async def _cmd_income(months: int) -> Reply:
    svc = get_service()
    parts: List[str] = []
    summary = None
    try:
        summary = await svc.income_summary(months=months)
        parts.append(render_income_summary(summary))
    except Exception:  # noqa: BLE001
        pass

    if summary and settings.partners and float(summary.get("total_rmb") or 0) > 0:
        total_rmb = float(summary["total_rmb"])
        shares = split_among_partners(int(round(total_rmb * 100)), settings.partners)
        parts.append(f"—— 团队分成（按预计实际收益 {total_rmb:,.2f} 元）——")
        parts.extend(partner_lines(shares))

    try:
        records = await svc.settlements()
        if records:
            parts.append(render_settlement(records))
    except Exception:  # noqa: BLE001
        pass

    try:
        data = await svc.monthly(months=months)
        eco = await svc.ecosystem_cost_rate()
        parts.append(render_income(data, eco))
    except Exception as exc:  # noqa: BLE001
        parts.append(f"规则推算查询失败：{exc}")

    return Reply(text="\n\n".join(parts))


async def _cmd_status() -> Reply:
    svc = get_service()
    try:
        info = await svc.client.get_user_info()
        official = await svc.account_overview()
        return Reply(text=render_status(True, info, official=official))
    except Exception as exc:  # noqa: BLE001
        return Reply(text=render_status(False, error=str(exc)))


async def _cmd_flashsale_apply(raw_date: str, item_id: str, num: int, is_admin: bool) -> Reply:
    if not is_admin:
        return Reply(text="仅群主或管理员可以提交秒杀申请。")
    if not (len(raw_date) == 8 and raw_date.isdigit()):
        return Reply(text="日期格式应为 YYYYMMDD，例如 20261016。")
    svc = get_service()
    try:
        info = await svc.flashsale_dates()
        allowed = {d["date"] for d in (info.get("dates") or [])}
        if allowed and raw_date not in allowed:
            return Reply(text=f"{raw_date} 不在可申请范围内，请先发送「秒杀」查看可申请日期。")
    except Exception:  # noqa: BLE001
        pass
    try:
        await svc.apply_flashsale(item_id=item_id, date=raw_date, num=num)
    except Exception as exc:  # noqa: BLE001
        return Reply(text=f"提交失败：{exc}")
    return Reply(
        text=f"已提交秒杀申请\n日期：{raw_date}\n作品ID：{item_id}\n限量：{num}\n"
        "可在「秒杀记录」中查看审核状态。"
    )


async def _cmd_dashboard(days: int) -> Reply:
    svc = get_service()
    ov = await svc.overview(days=days)
    rows = await svc.recent_daily(days=days)
    if not await _charts_on():
        return Reply(text=_chart_off_note() + "\n" + render_maps(ov, settings.chart_top_n))
    png = await _png(chart.render_dashboard, ov, rows, settings.chart_top_n)
    return Reply(image=png, caption=f"收益看板｜{ov.start_date} ~ {ov.end_date}")


async def _cmd_rank_chart(days: int) -> Reply:
    svc = get_service()
    ov = await svc.per_map(days=days)
    if not await _charts_on():
        return Reply(text=_chart_off_note() + "\n" + render_maps(ov, settings.chart_top_n))
    png = await _png(chart.render_map_rank, ov, settings.chart_top_n)
    return Reply(image=png, caption=f"各地图收益排行｜{ov.start_date} ~ {ov.end_date}")


async def _cmd_trend_chart(raw: str) -> Reply:
    svc = get_service()
    if raw:
        days = _parse_int(raw, default=14, lo=2, hi=365)
        rows = await svc.recent_daily(days=days)
    else:
        rows = await svc.trend_daily()
        days = max(len(rows), 1)
    if not await _charts_on():
        return Reply(text=_chart_off_note() + "\n" + render_trend(rows, days))
    png = await _png(chart.render_daily_trend, rows)
    return Reply(image=png, caption=f"每日钻石收益趋势｜共 {days} 天")


async def _cmd_monthly_chart(months: int) -> Reply:
    svc = get_service()
    data = await svc.monthly(months=months)
    if not await _charts_on():
        return Reply(text=_chart_off_note() + "\n" + render_monthly(data))
    png = await _png(chart.render_monthly, data)
    total = sum(m.total_diamond for m in data)
    return Reply(
        image=png,
        caption=f"各月钻石收益｜共 {len(data)} 个月\n区间总流水 {total:,} 钻石",
    )


# ----------------------------------------------------------------------
# 指令表
# ----------------------------------------------------------------------
_COMMANDS = {
    "收益": "overview", "总览": "overview", "overview": "overview", "sy": "overview",
    "地图": "maps", "地图收益": "maps", "作品": "maps", "maps": "maps",
    "昨日": "yesterday", "yesterday": "yesterday",
    "日均": "daily", "daily": "daily",
    "月报": "monthly", "月度": "monthly", "monthly": "monthly",
    "趋势": "trend", "trend": "trend",
    "余额": "balance", "钱包": "balance", "balance": "balance",
    "结算": "settlement", "官方结算": "settlement", "settlement": "settlement",
    "反馈": "feedback", "玩家反馈": "feedback", "feedback": "feedback",
    "退款反馈": "refund_feedback", "玩家退款反馈": "refund_feedback",
    "退款账单": "refund", "退款": "refund", "退款率": "refund", "refund": "refund",
    "数据": "analytics", "运营": "analytics", "日活": "analytics", "analytics": "analytics",
    "活动": "activities", "作品活动": "activities", "折扣特卖": "activities", "征集": "activities",
    "秒杀": "flashsale", "周末秒杀": "flashsale",
    "秒杀记录": "flashsale_log", "秒杀历史": "flashsale_log",
    "秒杀申请": "flashsale_apply", "申请秒杀": "flashsale_apply",
    "作品ID": "items_id", "模组ID": "items_id", "作品id": "items_id",
    "分成": "income", "实际收益": "income", "到账": "income", "income": "income",
    "状态": "status", "status": "status",
    "帮助": "help", "help": "help", "说明": "help",
    "图表": "dashboard", "收益图": "dashboard", "看板": "dashboard", "dashboard": "dashboard",
    "排行图": "rank_chart", "地图图": "rank_chart",
    "趋势图": "trend_chart",
    "月报图": "monthly_chart", "月度图": "monthly_chart",
}


async def handle(text: str, *, is_admin: bool = False) -> Reply:
    """把一条指令文本转成回复。未知指令返回帮助。"""
    raw = (text or "").strip()
    if not raw:
        return Reply(text=_help_text())

    parts = raw.split()
    head = parts[0].lstrip("/")
    args = parts[1:]
    rest = " ".join(args)
    action = _COMMANDS.get(head)

    try:
        if action == "overview":
            return await _cmd_overview(_parse_int(rest, 7))
        if action == "maps":
            return await _cmd_maps(_parse_int(rest, 7))
        if action == "yesterday":
            return await _cmd_yesterday()
        if action == "daily":
            return await _cmd_daily(_parse_int(rest, 7))
        if action == "monthly":
            return await _cmd_monthly(_parse_int(rest, 6, 1, 24))
        if action == "trend":
            return await _cmd_trend(_parse_int(rest, 7))
        if action == "balance":
            return await _cmd_balance()
        if action == "settlement":
            return await _cmd_settlement()
        if action == "feedback":
            return await _cmd_feedback()
        if action == "refund_feedback":
            return await _cmd_refund(_parse_int(rest, 30, 1, 180), "我的世界开发者收益 · 玩家退款反馈")
        if action == "refund":
            return await _cmd_refund(_parse_int(rest, 30, 1, 180), "我的世界开发者收益 · 退款账单")
        if action == "analytics":
            return await _cmd_analytics(_parse_int(rest, 7))
        if action == "activities":
            return await _cmd_activities()
        if action == "flashsale":
            return await _cmd_flashsale()
        if action == "flashsale_log":
            return await _cmd_flashsale_log()
        if action == "flashsale_apply":
            if len(args) < 2:
                return Reply(
                    text="用法：秒杀申请 日期 作品ID [限量]\n"
                    "例如：秒杀申请 20261016 4689696653497663244\n"
                    "可申请日期请先发送「秒杀」查看。"
                )
            num = 1000
            if len(args) >= 3:
                try:
                    num = int(args[2])
                except ValueError:
                    num = 1000
            return await _cmd_flashsale_apply(
                args[0].replace("-", ""), args[1], num, is_admin
            )
        if action == "items_id":
            return await _cmd_items_id()
        if action == "income":
            return await _cmd_income(_parse_int(rest, 6, 1, 12))
        if action == "status":
            return await _cmd_status()
        if action == "help":
            return Reply(text=_help_text())
        if action == "dashboard":
            return await _cmd_dashboard(_parse_int(rest, 14, 2, 90))
        if action == "rank_chart":
            return await _cmd_rank_chart(_parse_int(rest, 7, 1, 90))
        if action == "trend_chart":
            return await _cmd_trend_chart(rest)
        if action == "monthly_chart":
            return await _cmd_monthly_chart(_parse_int(rest, 6, 1, 24))
    except Exception as exc:  # noqa: BLE001
        return Reply(text=f"查询失败：{exc}")

    return Reply(text=_help_text())


async def warmup() -> None:
    """启动时预热：读取开发者昵称与头像，供图表 logo 使用。"""
    if not settings.show_profile:
        return
    try:
        from .profile import fetch_avatar

        prof = await get_service().profile()
        set_developer_name(prof.display_name)
        if chart.charts_available():
            path = await fetch_avatar(prof.avatar_url, settings.timeout)
            if path:
                chart.set_logo_path(path)
    except Exception:  # noqa: BLE001
        pass


__all__ = ["Reply", "handle", "get_service", "reset_service", "warmup"]
