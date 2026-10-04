"""我的世界开发者收益插件。

加载后会注册以下指令（支持中英文别名）：
    收益 / 总览 / overview
    地图 / 地图收益 / maps
    昨日 / yesterday
    日均 / daily
    月报 / monthly
    趋势 / trend
    状态 / status
    帮助 / help
"""
from __future__ import annotations

from . import handler  # noqa: F401  触发指令注册

__all__ = ["handler"]
