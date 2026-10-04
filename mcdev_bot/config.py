"""配置读取。

所有配置来自环境变量（可写在项目根目录的 ``.env`` 中）。
这里刻意不依赖 pydantic，方便在没有 NoneBot 环境时单独测试抓取模块。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

# 项目根目录（mcdev_bot 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:  # python-dotenv 可选
    from dotenv import load_dotenv

    # 显式指定 .env 路径，保证以服务方式运行时也能正确读取
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=False)
except Exception:  # pragma: no cover - 缺少依赖时静默跳过
    pass

from .revenue import Partner, parse_partners  # noqa: E402


# --------------------------------------------------------------------------
# ▍开发者平台接口映射（通过对 mcdev.webapp.163.com 前端资源分析得到）
# --------------------------------------------------------------------------
# 数据接口前缀：whichApi(platform)
#   pe/pc         -> "/"                    -> data_analysis/day_detail/
#   jpe/jpc       -> "/multi/"              -> data_analysis/multi/day_detail/
#   adv           -> "/adv/"                -> data_analysis/adv/day_detail/
#   lobby/jgpc... -> "/goods/"              -> data_analysis/goods/day_detail/
#   dape/dapc     -> "/day_fans_detail/"
PLATFORM_MAP: Dict[str, Dict[str, str]] = {
    "pe":    {"prefix": "/",       "platform": "pe", "category": "pe"},
    "pc":    {"prefix": "/",       "platform": "pc", "category": "comp"},
    "jpe":   {"prefix": "/multi/", "platform": "pe", "category": "pe_multi"},
    "jpc":   {"prefix": "/multi/", "platform": "pc", "category": "multi"},
    "adv":   {"prefix": "/adv/",   "platform": "pe", "category": "pe"},
    "lobby": {"prefix": "/goods/", "platform": "pe", "category": "pe"},
}

# 作品分类：用于 items/categories/{cate}/{id}/incomes/ 结算明细接口
INCOME_CATE_MAP: Dict[str, str] = {
    "pe": "pe",
    "pc": "comp",
    "jpe": "pe_multi",
    "jpc": "multi",
}


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> List[str]:
    raw = os.getenv(name) or ""
    return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]


def _env_int_list(name: str) -> List[int]:
    """解析形如 ``10,12,14`` 的整数列表，非法项自动忽略。"""
    result: List[int] = []
    for item in _env_list(name):
        try:
            result.append(int(item))
        except ValueError:
            continue
    return result


@dataclass
class Settings:
    """运行时配置。"""

    cookie: str = ""
    base_url: str = "https://mc-launcher.webapp.163.com/"
    platform: str = "pe"
    item_keyword: str = ""
    timeout: float = 20.0
    cache_ttl: int = 300
    mock: bool = False
    allowed_users: List[str] = None  # type: ignore[assignment]

    # 图表
    chart_enabled: bool = True
    chart_top_n: int = 8
    trend_start: str = ""        # 趋势图起始日期（YYYY-MM-DD）；留空取最近 90 天

    # 开发者身份展示（昵称 + 头像 logo）
    show_profile: bool = True

    # 启动时扫描指定群的成员（用于查找成员 QQ 号），留空则不扫描
    member_scan_group: str = ""

    # 收益分成计算
    ecosystem_cost_rate: float = 0.0     # 生态成本分摊比例（0~1）；0 表示自动按官方结算反推
    incentive_rate: float = 0.0          # 鼓励金额比例（鼓励金额 = 分成 × 该比例）；0 表示不计
    partners: List["Partner"] = None     # type: ignore[assignment]
    split_months: int = 12               # 汇总预计实际收益时回溯的月份数

    push_enabled: bool = False
    push_chart: bool = True
    push_split: bool = True      # 推送时附带团队贡献值分成（含 @）
    push_targets: List[str] = None  # type: ignore[assignment]
    push_hours: List[int] = None  # type: ignore[assignment]
    push_minute: int = 0

    # ---- 派生属性 ----
    @property
    def push_hours_expr(self) -> str:
        """供 APScheduler cron 使用的小时表达式，例如 ``10,12,14``。"""
        return ",".join(str(h) for h in (self.push_hours or [9]))

    @property
    def api_prefix(self) -> str:
        return PLATFORM_MAP.get(self.platform, PLATFORM_MAP["pe"])["prefix"]

    @property
    def api_platform(self) -> str:
        return PLATFORM_MAP.get(self.platform, PLATFORM_MAP["pe"])["platform"]

    @property
    def api_category(self) -> str:
        return PLATFORM_MAP.get(self.platform, PLATFORM_MAP["pe"])["category"]

    @property
    def use_mock(self) -> bool:
        """未配置 Cookie 或显式开启时使用演示数据。"""
        return self.mock or not self.cookie

    def reload(self) -> "Settings":
        """从环境变量重新加载。"""
        self.cookie = _env("MCDEV_COOKIE")
        self.base_url = _env("MCDEV_BASE_URL", "https://mc-launcher.webapp.163.com/")
        self.platform = _env("MCDEV_PLATFORM", "pe").lower() or "pe"
        self.item_keyword = _env("MCDEV_ITEM_KEYWORD")
        self.timeout = _env_float("MCDEV_TIMEOUT", 20.0)
        self.cache_ttl = _env_int("MCDEV_CACHE_TTL", 300)
        self.mock = _env_bool("MCDEV_MOCK", False)
        self.allowed_users = _env_list("MCDEV_ALLOWED_USERS")

        self.chart_enabled = _env_bool("MCDEV_CHART_ENABLED", True)
        self.chart_top_n = _env_int("MCDEV_CHART_TOP_N", 8)
        self.trend_start = _env("MCDEV_TREND_START")

        self.show_profile = _env_bool("MCDEV_SHOW_PROFILE", True)
        self.member_scan_group = _env("MCDEV_MEMBER_SCAN")
        self.ecosystem_cost_rate = _env_float("MCDEV_ECOSYSTEM_COST_RATE", 0.0)
        self.incentive_rate = _env_float("MCDEV_INCENTIVE_RATE", 0.0)
        self.partners = parse_partners(_env("MCDEV_PARTNERS"))
        self.split_months = max(1, min(_env_int("MCDEV_SPLIT_MONTHS", 12), 36))

        self.push_enabled = _env_bool("MCDEV_PUSH_ENABLED", False)
        self.push_chart = _env_bool("MCDEV_PUSH_CHART", True)
        self.push_split = _env_bool("MCDEV_PUSH_SPLIT", True)
        self.push_targets = _env_list("MCDEV_PUSH_TARGETS")
        # 支持「每天多个时间点」：MCDEV_PUSH_HOURS=10,12,14,16,18,20,22,0
        # 兼容旧写法（单值 MCDEV_PUSH_HOUR）
        hours = _env_int_list("MCDEV_PUSH_HOURS")
        if not hours:
            hours = [_env_int("MCDEV_PUSH_HOUR", 9)]
        self.push_hours = sorted({h for h in hours if 0 <= h <= 23})
        self.push_minute = _env_int("MCDEV_PUSH_MINUTE", 0)

        if not self.base_url.endswith("/"):
            self.base_url += "/"
        return self


settings = Settings()
settings.reload()


def reload_settings() -> Settings:
    """供测试或热加载使用。"""
    return settings.reload()


__all__ = ["Settings", "settings", "reload_settings", "PLATFORM_MAP", "INCOME_CATE_MAP"]
