"""官方 QQ 机器人启动入口（QQ 开放平台 · qq-botpy）。

与 ``bot.py``（NoneBot + NapCat）的区别：
- 不需要安装/运行 QQ 客户端，也不需要在开放平台之外配置 WebSocket 地址
- 只需在 ``.env`` 中填好 ``QQ_BOT_APPID`` 与 ``QQ_BOT_SECRET``
- 只有被动回复：群里 @机器人 或私聊机器人时才会响应

运行：
    python bot_qq.py
"""
from __future__ import annotations

import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
except Exception:  # pragma: no cover
    pass

from mcdev_bot import dispatcher  # noqa: E402
from mcdev_bot.config import settings  # noqa: E402


def _check_config() -> bool:
    if not settings.qq_appid or not settings.qq_secret:
        print(
            "============================================================\n"
            " 缺少官方机器人凭证\n"
            "============================================================\n"
            " 请先在 QQ 开放平台（https://q.qq.com/）创建机器人，\n"
            " 然后把 AppID 与 AppSecret 填入项目根目录的 .env：\n\n"
            "     QQ_BOT_APPID=你的AppID\n"
            "     QQ_BOT_SECRET=你的AppSecret\n\n"
            " 沙箱环境调试时再加一行： QQ_BOT_SANDBOX=true\n",
            flush=True,
        )
        return False
    return True


async def _warmup() -> None:
    await dispatcher.warmup()


def main() -> None:
    if not _check_config():
        sys.exit(1)

    mode = "演示数据" if settings.use_mock else "真实接口"
    print("============================================================", flush=True)
    print(" 我的世界开发者收益 QQ 机器人 · 官方机器人模式", flush=True)
    print("============================================================", flush=True)
    print(f" AppID    ：{settings.qq_appid}", flush=True)
    print(f" 沙箱环境 ：{'是' if settings.qq_sandbox else '否'}", flush=True)
    print(f" 数据模式 ：{mode}，平台：{settings.platform}", flush=True)
    print(" 使用方式 ：群里 @机器人 或私聊机器人，发送「帮助」查看指令", flush=True)
    print("============================================================", flush=True)

    # botpy.Client 在构造时会取「当前事件循环」（Python 3.12 下 asyncio.run 结束后会置空），
    # 因此这里显式新建并设置一个循环，并让预热与 client.run() 共用同一个循环：
    # 否则预热时建立的 HTTP 连接池会挂在已关闭的循环上，运行期报 "Event loop is closed"。
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_warmup())
    # 预热用的客户端不再复用，交给运行期在同一个循环里重建
    dispatcher.reset_service()

    from mcdev_bot.qqbot_bot import build_client

    client = build_client()
    client.run(appid=settings.qq_appid, secret=settings.qq_secret)


if __name__ == "__main__":
    main()
