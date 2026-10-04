"""图表渲染：把收益数据绘制成 PNG 图片，供 QQ 直接发送。

设计要点
--------
* 使用 matplotlib 的 Agg 后端（无界面），渲染结果写入内存，返回 ``bytes``；
* 自动探测中文字体（优先 Windows 系统字体，其次 Noto Sans CJK / 文泉驿），
  避免中文出现方框乱码；
* 若运行环境未安装 matplotlib，``charts_available()`` 返回 False，
  上层会自动降级为纯文本输出，不影响机器人运行。
"""
from __future__ import annotations

import io
import os
from datetime import datetime
from typing import List, Optional, Sequence

from .models import DailyRow, MapRevenue, MonthRevenue

# ----------------------------------------------------------------------
# 依赖探测
# ----------------------------------------------------------------------
try:  # pragma: no cover - 取决于运行环境
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager, rcParams
    from matplotlib.ticker import FuncFormatter

    _MPL_OK = True
except Exception:  # pragma: no cover
    _MPL_OK = False


# 常见中文字体候选路径（Windows / Linux）
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    r"C:\Windows\Fonts\simsun.ttc",     # 宋体
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

# 调色板
_COLORS = {
    "diamond": "#4C8DFF",
    "diamond_2": "#7AB0FF",
    "sales": "#FF9F43",
    "share": "#2ED573",
    "grid": "#E6E8EC",
    "text": "#2F3542",
    "bg": "#FFFFFF",
}

_font_ready = False
_logo_path: Optional[str] = None


def charts_available() -> bool:
    """当前环境是否可用图表功能。"""
    return _MPL_OK


def _find_cjk_font() -> Optional[str]:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _ensure_font() -> None:
    """初始化中文字体（幂等）。"""
    global _font_ready
    if _font_ready or not _MPL_OK:
        return
    # 按系统提示规范，优先显式指定 CJK 字体族
    families = ["Noto Sans CJK SC", "WenQuanYi Micro Hei"]
    path = _find_cjk_font()
    if path:
        try:
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            families.insert(0, name)
        except Exception:  # pragma: no cover
            pass
    families += ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    rcParams["font.sans-serif"] = families
    rcParams["axes.unicode_minus"] = False
    rcParams["figure.facecolor"] = _COLORS["bg"]
    rcParams["axes.facecolor"] = _COLORS["bg"]
    _font_ready = True


def _thousands(value, _pos=None) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(value) >= 1e8:
        return f"{value / 1e8:.1f}亿"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.1f}万"
    return f"{int(round(value)):,}"


def set_logo_path(path: Optional[str]) -> None:
    """设置开发者头像文件路径，作为图表左上角 logo。"""
    global _logo_path
    _logo_path = path or None


def _draw_logo(fig) -> None:
    """把开发者头像画到图表左上角（失败时静默跳过，不影响出图）。"""
    if not _logo_path or not os.path.exists(_logo_path):
        return
    try:
        import matplotlib.image as mpimg

        img = mpimg.imread(_logo_path)
        ax = fig.add_axes([0.015, 0.9, 0.055, 0.055], zorder=10)
        ax.imshow(img)
        ax.set_axis_off()
    except Exception:  # noqa: BLE001  头像绘制失败不应影响图表
        return


def _to_png(fig) -> bytes:
    _draw_logo(fig)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor=_COLORS["bg"])
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _padded_range(values: Sequence[float], pad: float = 0.16) -> tuple:
    """为折线图计算留白的纵轴范围，避免曲线过于平直。"""
    nums = [float(v) for v in values] or [0.0]
    lo, hi = min(nums), max(nums)
    if hi <= 0:
        return 0.0, 1.0
    span = hi - lo
    if span <= 0:
        span = hi * 0.2
    return max(0.0, lo - span * pad), hi + span * pad


def _short(name: str, limit: int = 22) -> str:
    """作品名截断：保留足够长度以免同名前缀的作品看起来完全一样。"""
    name = (name or "未命名作品").strip()
    return name if len(name) <= limit else name[: limit - 1] + "…"


def _annotate_points(ax, labels, values, max_labels: int = 20, top_n: int = 5) -> None:
    """给折线图加数值标签。

    点较少时全部标注；点较多时只标注最高的若干个，避免标签互相重叠。
    """
    count = len(labels)
    if not count:
        return
    if count <= max_labels:
        indexes = range(count)
    else:
        indexes = sorted(
            sorted(range(count), key=lambda i: values[i], reverse=True)[:top_n]
        )
    for i in indexes:
        ax.annotate(
            _thousands(values[i]),
            (labels[i], values[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=8,
            color=_COLORS["text"],
        )


def _style_axes(ax) -> None:
    ax.grid(axis="both", color=_COLORS["grid"], linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(_COLORS["grid"])
    ax.spines["bottom"].set_color(_COLORS["grid"])
    ax.tick_params(colors=_COLORS["text"], labelsize=9)


def _subtitle() -> str:
    from .config import settings
    from .formatter import PLATFORM_LABEL, get_developer_name

    label = PLATFORM_LABEL.get(settings.platform, settings.platform)
    dev = get_developer_name()
    tail = f"｜筛选：{settings.item_keyword}" if settings.item_keyword else ""
    source = "演示数据" if settings.use_mock else "开发者平台实时数据"
    head = f"{dev}｜" if dev else ""
    return f"{head}{label}{tail}｜{source}｜生成于 {datetime.now():%Y-%m-%d %H:%M}"


# ----------------------------------------------------------------------
# 各图表
# ----------------------------------------------------------------------
def render_map_rank(overview, top_n: int = 8) -> bytes:
    """各地图钻石收益排行（横向条形图）+ 销量标注。"""
    _ensure_font()
    maps: List[MapRevenue] = overview.maps[:top_n][::-1]  # 反转让第一名在上方
    names = [_short(m.name) for m in maps]
    values = [m.diamond for m in maps]

    fig, ax = plt.subplots(figsize=(10, max(3.2, 0.62 * len(maps) + 2.0)))
    bars = ax.barh(names, values, color=_COLORS["diamond"], height=0.62)
    for bar, item in zip(bars, maps):
        ax.text(
            bar.get_width() * 1.01,
            bar.get_y() + bar.get_height() / 2,
            f"{item.diamond:,} 钻石｜{item.sales:,} 份",
            va="center",
            ha="left",
            fontsize=9,
            color=_COLORS["text"],
        )
    ax.set_xlim(0, max(values) * 1.32 if values else 1)
    ax.xaxis.set_major_formatter(FuncFormatter(_thousands))
    ax.set_title(
        f"各地图钻石收益排行 TOP{len(maps)}　{overview.start_date} ~ {overview.end_date}",
        fontsize=13,
        color=_COLORS["text"],
        pad=14,
    )
    ax.set_xlabel(_subtitle(), fontsize=8, color="#8A8F99")
    _style_axes(ax)
    return _to_png(fig)


def render_daily_trend(rows: Sequence[DailyRow], title_suffix: str = "") -> bytes:
    """每日收益趋势（折线 + 面积）。"""
    _ensure_font()
    ordered = sorted([r for r in rows if r.dateid], key=lambda r: r.dateid)
    labels = [
        f"{r.dateid[4:6]}-{r.dateid[6:]}" if len(r.dateid) == 8 else r.dateid for r in ordered
    ]
    values = [r.diamond for r in ordered]
    sales = [r.cnt_buy for r in ordered]

    fig, ax = plt.subplots(figsize=(10, 4.4))
    if ordered:
        ax.plot(labels, values, marker="o", linewidth=2.2, color=_COLORS["diamond"], label="钻石收益")
        ax.fill_between(labels, values, color=_COLORS["diamond"], alpha=0.12)
        _annotate_points(ax, labels, values)
        ax.set_ylim(*_padded_range(values))

        ax2 = ax.twinx()
        ax2.plot(labels, sales, marker="s", linewidth=1.6, linestyle="--",
                 color=_COLORS["sales"], label="销量")
        ax2.set_ylabel("日销量（份）", fontsize=10, color=_COLORS["sales"])
        ax2.tick_params(axis="y", colors=_COLORS["sales"], labelsize=9)
        ax2.spines["top"].set_visible(False)
        ax2.set_ylim(*_padded_range(sales))

    ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
    ax.set_ylabel("钻石收益", fontsize=10, color=_COLORS["text"])
    ax.set_title(f"每日钻石收益趋势　{title_suffix}", fontsize=13, color=_COLORS["text"], pad=14)
    if len(labels) > 12:
        ax.set_xticks(labels[:: max(1, len(labels) // 12)])
    ax.set_xlabel(_subtitle(), fontsize=8, color="#8A8F99")
    _style_axes(ax)
    return _to_png(fig)


def render_monthly(months: Sequence[MonthRevenue]) -> bytes:
    """各月钻石收益（柱状图）。

    只展示「钻石收益」单一口径：开发者分成的真实值无法从日明细取得，
    为避免给出误导性数字，这里不做推算。
    """
    _ensure_font()
    ordered = sorted(months, key=lambda m: m.monthid)
    labels = []
    for m in ordered:
        mid = m.monthid
        labels.append(f"{mid[:4]}-{mid[4:]}" if len(mid) == 6 else mid)
    totals = [m.total_diamond for m in ordered]

    fig, ax = plt.subplots(figsize=(10, 4.8))
    bars = ax.bar(labels, totals, width=0.55, color=_COLORS["diamond"])
    for bar, value in zip(bars, totals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), _thousands(value),
                ha="center", va="bottom", fontsize=8.5, color=_COLORS["text"])
    ax.yaxis.set_major_formatter(FuncFormatter(_thousands))
    ax.set_ylim(0, (max(totals) * 1.18) if totals else 1)
    ax.set_title("各月钻石收益", fontsize=13, color=_COLORS["text"], pad=14)
    ax.set_ylabel("钻石", fontsize=10, color=_COLORS["text"])
    ax.set_xlabel(_subtitle(), fontsize=8, color="#8A8F99")
    _style_axes(ax)
    return _to_png(fig)


def render_dashboard(overview, rows: Sequence[DailyRow], top_n: int = 8) -> bytes:
    """综合收益看板：上方地图排行，下方每日趋势。"""
    _ensure_font()
    maps = overview.maps[:top_n][::-1]
    names = [_short(m.name) for m in maps]
    values = [m.diamond for m in maps]

    ordered = sorted([r for r in rows if r.dateid], key=lambda r: r.dateid)
    labels = [
        f"{r.dateid[4:6]}-{r.dateid[6:]}" if len(r.dateid) == 8 else r.dateid for r in ordered
    ]
    daily = [r.diamond for r in ordered]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10.5, 9.0), gridspec_kw={"height_ratios": [1.05, 1.0], "hspace": 0.42}
    )

    # —— 上：地图收益排行
    bars = ax1.barh(names, values, color=_COLORS["diamond"], height=0.6)
    for bar, item in zip(bars, maps):
        ax1.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                 f"{item.diamond:,}｜{item.sales:,} 份", va="center", ha="left",
                 fontsize=8.5, color=_COLORS["text"])
    ax1.set_xlim(0, (max(values) * 1.34) if values else 1)
    ax1.xaxis.set_major_formatter(FuncFormatter(_thousands))
    ax1.set_title(f"各地图钻石收益　{overview.start_date} ~ {overview.end_date}",
                  fontsize=12.5, color=_COLORS["text"], pad=10)
    _style_axes(ax1)

    # —— 下：每日趋势
    if ordered:
        ax2.plot(labels, daily, marker="o", linewidth=2.2, color=_COLORS["diamond"])
        ax2.fill_between(labels, daily, color=_COLORS["diamond"], alpha=0.12)
        ax2.set_ylim(*_padded_range(daily))
        _annotate_points(ax2, labels, daily)
        if len(labels) > 12:
            ax2.set_xticks(labels[:: max(1, len(labels) // 12)])
    ax2.yaxis.set_major_formatter(FuncFormatter(_thousands))
    ax2.set_title("每日钻石收益趋势", fontsize=12.5, color=_COLORS["text"], pad=10)
    _style_axes(ax2)

    fig.suptitle(
        f"开发者收益看板　总收益 {overview.total_diamond:,} 钻石（≈ "
        f"{overview.total_diamond / 100:,.2f} 元）｜销量 {overview.total_sales:,} 份",
        fontsize=14, color=_COLORS["text"], y=0.985,
    )
    fig.text(0.5, 0.005, _subtitle(), ha="center", fontsize=8, color="#8A8F99")
    return _to_png(fig)


__all__ = [
    "charts_available",
    "set_logo_path",
    "render_map_rank",
    "render_daily_trend",
    "render_monthly",
    "render_dashboard",
]
