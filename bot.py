"""QQ 机器人启动入口（NoneBot2 + OneBot v11）。

运行：
    python bot.py
前置条件见 README.md（需先启动 NapCat / Lagrange 等 OneBot 实现）。
"""
from __future__ import annotations

# 确保项目根目录在 sys.path 中，方便 `python bot.py` 直接运行
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)  # 统一工作目录，保证相对路径在任意平台/服务方式下一致

# 先加载 .env，保证 mcdev_bot.config 能读到环境变量
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_ROOT, ".env"), override=False)
except Exception:  # pragma: no cover
    pass

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# 初始化 NoneBot（自动读取 .env）
nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载收益查询插件
nonebot.load_plugin("mcdev_bot.plugins.revenue")

app = nonebot.get_asgi()


if __name__ == "__main__":
    nonebot.run()
