"""本地预览：把机器人的全部指令跑一遍并打印回复（无需 QQ / NapCat）。

用途
----
不启动 QQ 也能确认每条指令的实际输出效果：
  · 文字指令 -> 直接打印文本
  · 图表指令 -> 渲染成 PNG 保存到 ``preview/`` 目录，并打印文件路径

用法
----
    python tools/replay.py
    python tools/replay.py --days 30      # 指定总览/地图类指令的天数
    python tools/replay.py --no-chart     # 跳过图表（不装 matplotlib 时可用）

数据来源与 ``bot.py`` 完全一致：配置了有效 Cookie 就用真实数据，否则用演示数据。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
except Exception:  # pragma: no cover
    pass

from mcdev_bot import chart  # noqa: E402
from mcdev_bot.config import reload_settings  # noqa: E402
from mcdev_bot.formatter import (  # noqa: E402
    HELP_TEXT,
    partner_lines,
    render_daily_average,
    render_income,
    render_maps,
    render_monthly,
    render_overview,
    render_status,
    render_trend,
    render_yesterday,
    set_developer_name,
)
from mcdev_bot.profile import fetch_avatar  # noqa: E402
from mcdev_bot.revenue import split_among_partners  # noqa: E402
from mcdev_bot.service import RevenueService, build_client  # noqa: E402

LINE = "=" * 60
PREVIEW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "preview")


def title(text: str) -> None:
    print()
    print(LINE)
    print(f"指令：{text}")
    print(LINE)


async def main(args: argparse.Namespace) -> int:
    settings = reload_settings()
    client = build_client(settings)
    service = RevenueService(client, settings)
    days = args.days

    mode = "演示数据" if settings.use_mock else "真实接口"
    print(f"数据模式：{mode}｜平台：{settings.platform}")

    # 开发者身份（消息署名 + 图表 logo）
    if settings.show_profile and not settings.use_mock:
        try:
            prof = await service.profile()
            set_developer_name(prof.display_name)
            logo = await fetch_avatar(prof.avatar_url, settings.timeout)
            if logo:
                chart.set_logo_path(logo)
            print(f"开发者：{prof.display_name}｜头像：{'已加载' if logo else '无'}")
        except Exception:  # noqa: BLE001
            pass

    try:
        # 1. 收益 / 总览
        title(f"收益 {days}")
        print(render_overview(await service.overview(days=days), days))

        # 2. 地图
        title(f"地图 {days}")
        print(render_maps(await service.per_map(days=days)))

        # 3. 昨日
        title("昨日")
        print(render_yesterday(await service.yesterday()))

        # 4. 日均
        title(f"日均 {days}")
        print(render_daily_average(await service.daily_average(days=days), days))

        # 5. 月报
        title("月报 6")
        months = await service.monthly(months=6)
        print(render_monthly(months))

        # 6. 趋势
        title(f"趋势 {min(days, 30)}")
        print(render_trend(await service.recent_daily(days=min(days, 30)), min(days, 30)))

        # 7. 状态
        title("状态")
        if settings.use_mock:
            print(render_status(logged_in=False))
        else:
            try:
                user = await client.get_user_info()
                official = await service.account_overview()
                print(render_status(logged_in=True, user=user, official=official))
            except Exception as exc:  # noqa: BLE001
                print(render_status(logged_in=False, error=str(exc)))

        # 7.5 分成（按最新规则算实际到账 + 团队贡献值）
        title("分成 3")
        months_data = await service.monthly(months=3)
        print(render_income(months_data, settings.ecosystem_cost_rate))
        total_share = sum(m.developer_share for m in months_data)
        shares = split_among_partners(total_share, settings.partners or [])
        if shares:
            print()
            print(f"—— 团队贡献值分成（合计 {total_share:,} 钻石）——")
            for line in partner_lines(shares):
                print("   ", line)

        # 8~11. 图表
        if args.no_chart:
            title("图表指令")
            print("已通过 --no-chart 跳过。")
        elif not chart.charts_available():
            title("图表指令")
            print("当前环境未安装 matplotlib，图表指令会降级为文字。")
        else:
            os.makedirs(PREVIEW_DIR, exist_ok=True)
            ov = await service.overview(days=days)
            rows = await service.recent_daily(days=days)
            # 趋势图与看板使用「起始日 → 现在」的完整区间
            full_rows = await service.trend_daily()
            full_ov = await service.trend_overview()
            span = f"{service.trend_start_date()} ~ {service.latest_day}"
            boards = {
                "图表": (
                    "dashboard.png",
                    chart.render_dashboard,
                    (full_ov, full_rows, settings.chart_top_n),
                ),
                "排行图": ("rank.png", chart.render_map_rank, (ov, settings.chart_top_n)),
                "趋势图": ("trend.png", chart.render_daily_trend, (full_rows, span)),
                "月报图": ("monthly.png", chart.render_monthly, (months,)),
            }
            for cmd, (filename, func, func_args) in boards.items():
                title(f"{cmd}（图片）")
                png = func(*func_args)
                path = os.path.join(PREVIEW_DIR, filename)
                with open(path, "wb") as fp:
                    fp.write(png)
                print(f"已生成图片：{path}（{len(png)} 字节）")

        # 12. 帮助
        title("帮助")
        print(HELP_TEXT)

    finally:
        await client.aclose()

    print()
    print(LINE)
    print("预览完成。")
    if not args.no_chart and chart.charts_available():
        print(f"图片目录：{PREVIEW_DIR}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="本地预览机器人的全部指令回复")
    parser.add_argument("--days", type=int, default=7, help="总览/地图/趋势类指令的天数，默认 7")
    parser.add_argument("--no-chart", action="store_true", help="跳过图表渲染")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
