"""指令注册与消息处理。"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import List, Optional

from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.log import logger
from nonebot.params import CommandArg

from ... import chart
from ...config import settings
from ...formatter import (
    HELP_TEXT,
    partner_lines,
    render_daily_average,
    render_income,
    render_income_summary,
    render_maps,
    render_monthly,
    render_overview,
    render_settlement,
    render_status,
    render_trend,
    render_yesterday,
    set_developer_name,
)
from ...profile import fetch_avatar
from ...revenue import split_among_partners
from ...service import RevenueService, build_client

# ----------------------------------------------------------------------
# 单例：客户端 + 业务服务
# ----------------------------------------------------------------------
_service: Optional[RevenueService] = None


def get_service() -> RevenueService:
    global _service
    if _service is None:
        _service = RevenueService(build_client(settings), settings)
    return _service


def reset_service() -> None:
    """配置变化后重建（例如重载 .env）。"""
    global _service
    _service = None


# ----------------------------------------------------------------------
# 权限
# ----------------------------------------------------------------------
def _allowed(event: MessageEvent) -> bool:
    allowed = settings.allowed_users or []
    if not allowed:
        return True
    user_id = str(getattr(event, "user_id", "") or "")
    return user_id in allowed


def _fmt_day(dateid: str) -> str:
    """把 YYYYMMDD 显示为 YYYY-MM-DD。"""
    text = str(dateid or "")
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _parse_range(text: str, default: int, lo: int = 1, hi: int = 365) -> int:
    text = (text or "").strip()
    if not text:
        return default
    try:
        value = int(text)
    except ValueError:
        return default
    return max(lo, min(hi, value))


async def _guard(matcher, event: MessageEvent) -> bool:
    if not _allowed(event):
        await matcher.finish("你没有权限查询该账号的收益数据。")
        return False
    return True


# ----------------------------------------------------------------------
# 图表工具
# ----------------------------------------------------------------------
def _charts_on() -> bool:
    """图表功能是否可用（开关打开且运行环境已安装 matplotlib）。"""
    return settings.chart_enabled and chart.charts_available()


async def _render_png(func, *args, **kwargs) -> bytes:
    """在线程池中渲染图片，避免阻塞事件循环。"""
    return await asyncio.to_thread(func, *args, **kwargs)


def _image_message(caption: str, png: bytes) -> Message:
    return Message(MessageSegment.text(caption)) + MessageSegment.image(png)


def _chart_fallback_note() -> str:
    if not settings.chart_enabled:
        return "（图表功能已在配置中关闭，以下为文字版）"
    return "（当前环境未安装 matplotlib，以下为文字版。安装：python -m pip install matplotlib）"


# ----------------------------------------------------------------------
# 群成员查询（用于查找团队成员 QQ 号）
# ----------------------------------------------------------------------
async def _scan_group_members(group_id: int) -> list:
    """获取群成员列表。"""
    from nonebot import get_bots

    bots = get_bots()
    if not bots:
        return []
    bot: Bot = next(iter(bots.values()))
    try:
        members = await bot.get_group_member_list(group_id=group_id)
    except Exception:  # noqa: BLE001
        logger.exception("获取群成员列表失败")
        return []
    return list(members or [])


def _member_display(member: dict) -> str:
    card = (member.get("card") or "").strip()
    nick = (member.get("nickname") or "").strip()
    if card and nick and card != nick:
        return f"{card}（{nick}）"
    return card or nick or "（无昵称）"


def _match_partner(member: dict) -> str:
    """判断该成员是否命中 MCDEV_PARTNERS 里的某位成员，返回其名字。"""
    haystack = " ".join(
        str(member.get(k) or "") for k in ("card", "nickname", "remark")
    ).lower()
    for partner in settings.partners or []:
        key = (partner.name or "").strip().lower()
        if key and key in haystack:
            return partner.name
    return ""


def _format_member_list(group_id: int, members: list) -> str:
    lines = [f"群 {group_id} 成员（共 {len(members)} 人）", ""]
    hits = []
    for member in members:
        qq = member.get("user_id")
        matched = _match_partner(member)
        flag = "★" if matched else "·"
        line = f"{flag} {_member_display(member)}　QQ: {qq}"
        if matched:
            line += f"　← 匹配「{matched}」"
            hits.append((matched, qq, _member_display(member)))
        lines.append(line)
    if hits:
        lines.append("")
        lines.append("匹配到的团队成员：")
        for name, qq, display in hits:
            lines.append(f"  {name} -> {qq}（{display}）")
    lines.append("")
    lines.append("提示：把上面的 QQ 号填到 .env 的 MCDEV_PARTNERS 即可 @ 到人。")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# 指令
# ----------------------------------------------------------------------
overview_cmd = on_command("收益", aliases={"总览", "overview", "sy"}, priority=5, block=True)
maps_cmd = on_command("地图", aliases={"地图收益", "作品", "maps", "map"}, priority=5, block=True)
yesterday_cmd = on_command("昨日", aliases={"zuori", "yesterday"}, priority=5, block=True)
daily_cmd = on_command("日均", aliases={"daily", "rijun"}, priority=5, block=True)
monthly_cmd = on_command("月报", aliases={"月度", "monthly", "yuebao"}, priority=5, block=True)
trend_cmd = on_command("趋势", aliases={"trend", "qushi"}, priority=5, block=True)
status_cmd = on_command("状态", aliases={"status", "zhuangtai"}, priority=5, block=True)
help_cmd = on_command("帮助", aliases={"help", "说明"}, priority=5, block=True)

# —— 图表指令 ——
dashboard_cmd = on_command("图表", aliases={"收益图", "看板", "chart", "dashboard"}, priority=5, block=True)
rank_cmd = on_command("排行图", aliases={"地图图", "rankchart"}, priority=5, block=True)
trend_cmd_img = on_command("趋势图", aliases={"trendchart"}, priority=5, block=True)
monthly_cmd_img = on_command("月报图", aliases={"月度图", "monthchart"}, priority=5, block=True)

# —— 实际到账 / 团队分成 ——
income_cmd = on_command(
    "分成",
    aliases={"收益分成", "实际收益", "到账", "income", "split"},
    priority=5,
    block=True,
)

# —— 官方结算（平台真实数据）——
settle_cmd = on_command(
    "结算",
    aliases={"官方结算", "收益结算", "结算单", "settlement"},
    priority=5,
    block=True,
)

# —— 群成员查询（查找团队成员 QQ 号）——
members_cmd = on_command(
    "成员",
    aliases={"群成员", "查成员", "members"},
    priority=5,
    block=True,
)

# —— 手动触发推送 ——
pushtest_cmd = on_command(
    "推送测试",
    aliases={"测试推送", "pushtest"},
    priority=5,
    block=True,
)


@overview_cmd.handle()
async def _handle_overview(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(overview_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=7)
    try:
        ov = await get_service().overview(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询总览失败")
        await overview_cmd.finish(f"查询失败：{exc}")
        return
    await overview_cmd.finish(render_overview(ov, days))


@maps_cmd.handle()
async def _handle_maps(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(maps_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=7)
    try:
        ov = await get_service().per_map(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询地图收益失败")
        await maps_cmd.finish(f"查询失败：{exc}")
        return
    await maps_cmd.finish(render_maps(ov))


@yesterday_cmd.handle()
async def _handle_yesterday(event: MessageEvent):
    if not await _guard(yesterday_cmd, event):
        return
    try:
        ov = await get_service().yesterday()
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询昨日收益失败")
        await yesterday_cmd.finish(f"查询失败：{exc}")
        return
    await yesterday_cmd.finish(render_yesterday(ov))


@daily_cmd.handle()
async def _handle_daily(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(daily_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=7)
    try:
        ov = await get_service().daily_average(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询日均收益失败")
        await daily_cmd.finish(f"查询失败：{exc}")
        return
    await daily_cmd.finish(render_daily_average(ov, days))


@monthly_cmd.handle()
async def _handle_monthly(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(monthly_cmd, event):
        return
    months = _parse_range(args.extract_plain_text(), default=6, lo=1, hi=36)
    try:
        data = await get_service().monthly(months=months)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询月报失败")
        await monthly_cmd.finish(f"查询失败：{exc}")
        return
    await monthly_cmd.finish(render_monthly(data))


@trend_cmd.handle()
async def _handle_trend(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(trend_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=7, lo=1, hi=90)
    try:
        rows = await get_service().recent_daily(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询趋势失败")
        await trend_cmd.finish(f"查询失败：{exc}")
        return
    await trend_cmd.finish(render_trend(rows, days))


@status_cmd.handle()
async def _handle_status(event: MessageEvent):
    if not _allowed(event):
        await status_cmd.finish("你没有权限查询该账号的收益数据。")
        return
    if settings.use_mock:
        await status_cmd.finish(render_status(logged_in=False))
        return
    client = get_service().client
    try:
        user = await client.get_user_info()
        official = None
        try:
            official = await get_service().account_overview()
        except Exception:  # noqa: BLE001
            logger.exception("读取平台总览失败")
        await status_cmd.finish(render_status(logged_in=True, user=user, official=official))
    except Exception as exc:  # noqa: BLE001
        await status_cmd.finish(render_status(logged_in=False, error=str(exc)))


@help_cmd.handle()
async def _handle_help():
    await help_cmd.finish(HELP_TEXT)


# ----------------------------------------------------------------------
# 图表指令（渲染为图片发送）
# ----------------------------------------------------------------------
@dashboard_cmd.handle()
async def _handle_dashboard(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(dashboard_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=14, lo=2, hi=90)
    svc = get_service()
    try:
        ov = await svc.overview(days=days)
        rows = await svc.recent_daily(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成收益看板失败")
        await dashboard_cmd.finish(f"查询失败：{exc}")
        return
    if not _charts_on():
        await dashboard_cmd.finish(_chart_fallback_note() + "\n" + render_maps(ov))
        return
    try:
        png = await _render_png(chart.render_dashboard, ov, rows, settings.chart_top_n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("渲染收益看板失败")
        await dashboard_cmd.finish(f"生成图表失败：{exc}\n\n" + render_maps(ov))
        return
    caption = (
        f"开发者收益看板｜{ov.start_date} ~ {ov.end_date}\n"
        f"总收益 {ov.total_diamond:,} 钻石（≈ {ov.total_diamond / 100:,.2f} 元）"
        f"｜销量 {ov.total_sales:,} 份"
    )
    await dashboard_cmd.finish(_image_message(caption, png))


@rank_cmd.handle()
async def _handle_rank_chart(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(rank_cmd, event):
        return
    days = _parse_range(args.extract_plain_text(), default=7, lo=1, hi=90)
    svc = get_service()
    try:
        ov = await svc.per_map(days=days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成地图排行图失败")
        await rank_cmd.finish(f"查询失败：{exc}")
        return
    if not _charts_on():
        await rank_cmd.finish(_chart_fallback_note() + "\n" + render_maps(ov))
        return
    try:
        png = await _render_png(chart.render_map_rank, ov, settings.chart_top_n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("渲染地图排行图失败")
        await rank_cmd.finish(f"生成图表失败：{exc}\n\n" + render_maps(ov))
        return
    caption = (
        f"各地图收益排行｜{ov.start_date} ~ {ov.end_date}\n"
        f"合计 {ov.total_diamond:,} 钻石｜销量 {ov.total_sales:,} 份"
    )
    await rank_cmd.finish(_image_message(caption, png))


@trend_cmd_img.handle()
async def _handle_trend_chart(event: MessageEvent, args: Message = CommandArg()):
    """趋势图：不带参数展示「起始日 → 现在」的完整趋势，带天数则只看最近 N 天。"""
    if not await _guard(trend_cmd_img, event):
        return
    raw = args.extract_plain_text().strip()
    svc = get_service()
    try:
        if raw:
            days = _parse_range(raw, default=14, lo=2, hi=365)
            rows = await svc.recent_daily(days=days)
        else:
            rows = await svc.trend_daily()
            days = max(len(rows), 1)
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成收益趋势图失败")
        await trend_cmd_img.finish(f"查询失败：{exc}")
        return

    if not _charts_on():
        await trend_cmd_img.finish(_chart_fallback_note() + "\n" + render_trend(rows, days))
        return

    ordered = sorted([r for r in rows if r.dateid], key=lambda r: r.dateid)
    span_text = "最近 %d 天" % days
    if ordered:
        span_text = f"{_fmt_day(ordered[0].dateid)} ~ {_fmt_day(ordered[-1].dateid)}"
    try:
        png = await _render_png(chart.render_daily_trend, rows, span_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("渲染收益趋势图失败")
        await trend_cmd_img.finish(f"生成图表失败：{exc}\n\n" + render_trend(rows, days))
        return
    total = sum(r.diamond for r in ordered)
    caption = f"每日钻石收益趋势｜{span_text}\n区间合计 {total:,} 钻石（≈ {total / 100:,.2f} 元）"
    await trend_cmd_img.finish(_image_message(caption, png))


@monthly_cmd_img.handle()
async def _handle_monthly_chart(event: MessageEvent, args: Message = CommandArg()):
    if not await _guard(monthly_cmd_img, event):
        return
    months = _parse_range(args.extract_plain_text(), default=6, lo=1, hi=24)
    svc = get_service()
    try:
        data = await svc.monthly(months=months)
    except Exception as exc:  # noqa: BLE001
        logger.exception("生成月报图失败")
        await monthly_cmd_img.finish(f"查询失败：{exc}")
        return
    if not _charts_on():
        await monthly_cmd_img.finish(_chart_fallback_note() + "\n" + render_monthly(data))
        return
    try:
        png = await _render_png(chart.render_monthly, data)
    except Exception as exc:  # noqa: BLE001
        logger.exception("渲染月报图失败")
        await monthly_cmd_img.finish(f"生成图表失败：{exc}\n\n" + render_monthly(data))
        return
    total = sum(m.total_diamond for m in data)
    caption = f"各月钻石收益｜共 {len(data)} 个月\n区间总流水 {total:,} 钻石（≈ {total / 100:,.2f} 元）"
    await monthly_cmd_img.finish(_image_message(caption, png))


def _append_partners(message: Message, shares, heading: str) -> Message:
    """把团队分成（含 @）追加到消息里。"""
    if not shares:
        return message
    message += MessageSegment.text(f"\n\n{heading}\n")
    for share, line in zip(shares, partner_lines(shares)):
        if share.partner.qq:
            message += MessageSegment.at(share.partner.qq)
            message += MessageSegment.text(f" {line}\n")
        else:
            message += MessageSegment.text(f"{line}\n")
    return message


@settle_cmd.handle()
async def _handle_settlement(event: MessageEvent):
    """展示平台官方结算记录（真实数值）。"""
    if not await _guard(settle_cmd, event):
        return
    try:
        records = await get_service().settlements()
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询官方结算失败")
        await settle_cmd.finish(f"查询失败：{exc}")
        return
    await settle_cmd.finish(render_settlement(records))


@income_cmd.handle()
async def _handle_income(event: MessageEvent, args: Message = CommandArg()):
    """预计实际收益 = 官方已结算 + 未结算预估，并按贡献值 @ 成员。"""
    if not await _guard(income_cmd, event):
        return
    months_n = _parse_range(args.extract_plain_text(), default=6, lo=1, hi=12)
    svc = get_service()
    message = Message()

    # ① 预计实际收益（官方已结算 + 未结算预估）
    summary = None
    try:
        summary = await svc.income_summary(months=months_n)
        message += MessageSegment.text(render_income_summary(summary))
    except Exception:  # noqa: BLE001
        logger.exception("汇总预计实际收益失败")

    # ② 团队分成（按预计实际收益合计）
    if summary and settings.partners and float(summary.get("total_rmb") or 0) > 0:
        total_rmb = float(summary["total_rmb"])
        message = _append_partners(
            message,
            split_among_partners(int(round(total_rmb * 100)), settings.partners),
            f"—— 团队分成（按预计实际收益 {total_rmb:,.2f} 元）——",
        )

    # ③ 官方结算明细（平台真实数据）
    try:
        records = await svc.settlements()
        if records:
            message += MessageSegment.text("\n\n" + render_settlement(records))
    except Exception:  # noqa: BLE001
        logger.exception("查询官方结算失败")

    # ④ 规则推算（原本保留，作为参考）
    try:
        data = await svc.monthly(months=months_n)
    except Exception as exc:  # noqa: BLE001
        logger.exception("查询规则推算收益失败")
        message += MessageSegment.text(f"\n\n规则推算查询失败：{exc}")
        await income_cmd.finish(message)
        return

    eco_rate = await svc.ecosystem_cost_rate()
    message += MessageSegment.text("\n\n" + render_income(data, eco_rate))
    await income_cmd.finish(message)


@members_cmd.handle()
async def _handle_members(event: MessageEvent):
    """列出当前群成员及 QQ 号，并标出命中 MCDEV_PARTNERS 的成员。"""
    if not await _guard(members_cmd, event):
        return
    group_id = getattr(event, "group_id", None)
    if not group_id:
        await members_cmd.finish("该指令需要在群里使用。")
        return
    members = await _scan_group_members(int(group_id))
    if not members:
        await members_cmd.finish("未能获取群成员列表（可能机器人不在该群）。")
        return
    await members_cmd.finish(_format_member_list(int(group_id), members))


@pushtest_cmd.handle()
async def _handle_pushtest(event: MessageEvent, args: Message = CommandArg()):
    """立即执行一次收益推送，用于预览效果。

    用法：``推送测试``（推送到配置的目标）或 ``推送测试 群号或QQ号``。
    """
    if not await _guard(pushtest_cmd, event):
        return
    raw = args.extract_plain_text().strip()
    targets = (
        [t.strip() for t in raw.replace("，", ",").split(",") if t.strip()] if raw else None
    )
    if targets is None and not settings.push_targets:
        await pushtest_cmd.finish("未配置推送目标。用法：推送测试 群号或QQ号")
        return

    await pushtest_cmd.send("正在生成推送内容…")
    try:
        count = await _do_push(targets)
    except Exception as exc:  # noqa: BLE001
        logger.exception("手动推送失败")
        await pushtest_cmd.finish(f"推送失败：{exc}")
        return
    if count:
        await pushtest_cmd.finish(f"已推送 {count} 个目标。")
    else:
        await pushtest_cmd.finish("推送失败，请查看机器人日志。")


# ----------------------------------------------------------------------
# 推送内容构建与投递（定时任务与「推送测试」指令共用）
# ----------------------------------------------------------------------
async def _build_push_message() -> Message:
    """构建一条推送消息：昨日收益 + 团队分成（含 @）+ 近 14 天看板图。"""
    svc = get_service()
    # 平台数据有发布延迟，取「最近一个有数据的日期」，避免刚过零点推成全 0
    ov = await svc.latest_available()
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    title = (
        "我的世界开发者收益 · 昨日"
        if ov.end_date == yesterday_str
        else "我的世界开发者收益 · 最新可用数据"
    )
    message = Message(MessageSegment.text(render_yesterday(ov, title=title)))

    # 预计实际收益（官方已结算 + 未结算预估）与团队分成
    if settings.push_split and settings.partners:
        summary = None
        try:
            summary = await svc.income_summary(months=settings.split_months)
        except Exception:  # noqa: BLE001
            logger.exception("推送汇总预计实际收益失败")

        if summary:
            settled = float(summary.get("settled_rmb") or 0)
            pending = float(summary.get("pending_rmb") or 0)
            total = float(summary.get("total_rmb") or 0)
            settled_months = "、".join(summary.get("settled_months") or []) or "无"
            pending_months = "、".join(summary.get("pending_months") or []) or "无"
            message += MessageSegment.text(
                f"\n\n—— 预计实际收益 ——\n"
                f"官方已结算：{settled:,.2f} 元（{settled_months}）\n"
                f"未结算预估：{pending:,.2f} 元（{pending_months}）\n"
                f"合计：{total:,.2f} 元"
            )
            if total > 0:
                message = _append_partners(
                    message,
                    split_among_partners(int(round(total * 100)), settings.partners),
                    f"—— 团队分成（按预计实际收益 {total:,.2f} 元）——",
                )

    # 附带收益看板图（起始日 → 现在，可通过 MCDEV_PUSH_CHART=false 关闭）
    if settings.push_chart and _charts_on():
        try:
            rows = await svc.trend_daily()
            board = await svc.trend_overview()
            png = await _render_png(chart.render_dashboard, board, rows, settings.chart_top_n)
            message += MessageSegment.image(png)
        except Exception:  # noqa: BLE001
            logger.exception("推送渲染图表失败，已降级为纯文本")
    return message


async def _deliver(bot: Bot, message: Message, targets: Optional[List[str]] = None) -> int:
    """把消息投递到目标（群号或 QQ 号），返回成功数量。"""
    ok = 0
    for target in (targets if targets is not None else settings.push_targets):
        try:
            if target.isdigit() and len(target) >= 6:
                await bot.send_group_msg(group_id=int(target), message=message)
            else:
                await bot.send_private_msg(user_id=int(target), message=message)
            ok += 1
            logger.info("已向 {} 推送收益", target)
        except Exception:  # noqa: BLE001
            logger.exception("推送到 {} 失败", target)
    return ok


async def _do_push(targets: Optional[List[str]] = None) -> int:
    """执行一次推送（定时任务与手动指令共用），返回成功投递数。"""
    from nonebot import get_bots

    bots = get_bots()
    if not bots:
        logger.warning("收益推送跳过：当前没有已连接的 OneBot")
        return 0
    bot: Bot = next(iter(bots.values()))
    try:
        message = await _build_push_message()
    except Exception as exc:  # noqa: BLE001
        logger.exception("推送获取数据失败")
        message = Message(f"收益推送失败：{exc}")
    return await _deliver(bot, message, targets)


# ----------------------------------------------------------------------
# 定时推送（可选，支持每天多个时间点）
# ----------------------------------------------------------------------
def _register_push() -> None:
    if not settings.push_enabled or not settings.push_targets:
        return
    try:
        from nonebot_plugin_apscheduler import scheduler
    except ImportError:  # pragma: no cover
        logger.warning("未安装 nonebot-plugin-apscheduler，跳过每日推送注册")
        return

    @scheduler.scheduled_job(
        "cron",
        hour=settings.push_hours_expr,
        minute=settings.push_minute,
        id="mcdev_daily_push",
    )
    async def _push() -> None:
        await _do_push()

    logger.info(
        "已注册收益推送：每天 {} 时 {:02d} 分 -> {}",
        settings.push_hours_expr,
        settings.push_minute,
        settings.push_targets,
    )


_driver = get_driver()


async def _load_profile() -> None:
    """读取开发者昵称与头像，用于消息署名与图表 logo。"""
    if not settings.show_profile:
        return
    try:
        prof = await get_service().profile()
        set_developer_name(prof.display_name)

        logo_state = "未启用"
        if chart.charts_available():
            logo_state = "无头像"
            path = await fetch_avatar(prof.avatar_url, settings.timeout)
            if path:
                chart.set_logo_path(path)
                logo_state = "已加载"
        logger.info("开发者身份：{}｜头像：{}", prof.display_name, logo_state)
    except Exception:  # noqa: BLE001
        logger.exception("读取开发者资料失败（不影响收益查询）")


async def _startup_member_scan() -> None:
    """启动后扫描指定群成员（MCDEV_MEMBER_SCAN），便于查找团队成员 QQ 号。"""
    await asyncio.sleep(15)  # 等待 OneBot 连接建立
    raw = settings.member_scan_group
    try:
        group_id = int(raw)
    except (TypeError, ValueError):
        logger.warning("MCDEV_MEMBER_SCAN 不是合法群号：{}", raw)
        return
    members = await _scan_group_members(group_id)
    if not members:
        logger.warning("群 {} 成员扫描失败（机器人可能不在该群）", group_id)
        return
    logger.info("群 {} 成员扫描结果：\n{}", group_id, _format_member_list(group_id, members))


@_driver.on_startup
async def _on_startup() -> None:
    mode = "演示数据" if settings.use_mock else "真实接口"
    logger.info("mcdev 收益插件已启动，数据模式：{}，平台：{}", mode, settings.platform)
    await _load_profile()
    _register_push()
    if settings.member_scan_group:
        asyncio.create_task(_startup_member_scan())


@_driver.on_shutdown
async def _on_shutdown() -> None:
    service = _service
    if service is not None:
        await service.client.aclose()
