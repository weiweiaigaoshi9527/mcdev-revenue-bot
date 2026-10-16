"""连通性自检脚本：验证 Cookie 是否有效、接口是否可读。

用法：
    python tools/probe.py
    python tools/probe.py --days 7          # 顺便打印最近 7 天各地图收益

若未配置 MCDEV_COOKIE，则会自动使用演示数据，便于先确认代码链路是否通畅。
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

from mcdev_bot.client import McDevClient, McDevError  # noqa: E402
from mcdev_bot.config import reload_settings  # noqa: E402
from mcdev_bot.formatter import render_maps, render_status  # noqa: E402
from mcdev_bot.mock import MockClient  # noqa: E402
from mcdev_bot.service import RevenueService  # noqa: E402

# 网易通行证会话 Cookie 的常见特征（仅用于提示，不校验具体值）
_COOKIE_HINTS = (
    "NTES_SESS",
    "NTES_PASSPORT",
    "NTES_OSESS",
    "S_INFO",
    "P_INFO",
    "URS_",
    "NETEASE_",
)


def diagnose_cookie(cookie: str) -> None:
    """登录失败时给出 Cookie 诊断信息（只显示字段名，不显示值）。"""
    parts = [p for p in cookie.split(";") if "=" in p]
    names = [p.split("=", 1)[0].strip() for p in parts]
    print(f"       当前 Cookie 含 {len(names)} 个字段：{', '.join(names) or '（空）'}")
    hit = any(any(h.lower() in n.lower() for h in _COOKIE_HINTS) for n in names)
    if not hit:
        print("       ✗ 未发现网易通行证会话字段（通常为 NTES_SESS 等）。")
        print("         请复制【请求头里的完整 Cookie】，而不是单个自定义字段。")
        print("         获取步骤见 README.md 第三节「获取开发者平台 Cookie」。")


async def main(days: int) -> int:
    settings = reload_settings()

    print("=" * 56)
    print("我的世界开发者平台 · 连通性自检")
    print("=" * 56)
    print(f"接口基址 : {settings.base_url}")
    print(f"统计平台 : {settings.platform}")
    print(f"数据模式 : {'演示数据（未配置 Cookie）' if settings.use_mock else '真实接口'}")
    if settings.item_keyword:
        print(f"名称筛选 : {settings.item_keyword}")
    print("-" * 56)

    if settings.use_mock:
        client = MockClient(settings)
    else:
        client = McDevClient(settings)
        try:
            info = await client.get_user_info()
            print("[OK] 登录态有效")
            print(render_status(True, info))
        except McDevError as exc:
            print("[FAIL] 登录态校验失败：", exc)
            diagnose_cookie(settings.cookie)
            print(render_status(False, error=str(exc)))
            await client.aclose()
            return 2

    service = RevenueService(client, settings)
    try:
        items = await service.items()
        print(f"名下作品：{len(items)} 个")
        for it in items[:10]:
            print(f"  · {it.item_name}")
        official = await service.account_overview()
        print("-" * 56)
        print("平台官方口径：")
        print(f"  昨日钻石：{official.get('yesterday_diamond', 0)}")
        print(f"  近 14 天合计：{official.get('days_14_total_diamond', 0)}"
              f"｜日均：{official.get('days_14_average_diamond', 0)}")
        print(f"  本月：{official.get('this_month_diamond', 0)}"
              f"｜上月：{official.get('last_month_diamond', 0)}")
        overview = await service.per_map(days=days)
        print("-" * 56)
        print(render_maps(overview))
    except McDevError as exc:
        print("[FAIL] 拉取收益数据失败：", exc)
        await client.aclose()
        return 3

    await client.aclose()
    print("-" * 56)
    print("自检完成。")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="开发者平台接口连通性自检")
    parser.add_argument("--days", type=int, default=7, help="统计最近多少天，默认 7")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.days)))
