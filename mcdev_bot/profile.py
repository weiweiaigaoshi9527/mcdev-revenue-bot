"""开发者身份信息：昵称与头像（用于消息署名与图表 logo）。

数据来源：开发者平台 ``users/me`` 接口，字段 ``nickname`` / ``head_img``。

头像下载后缓存到项目下的 ``.cache/`` 目录，避免每次渲染图表都重新下载。
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Optional

import httpx

# 项目根目录（mcdev_bot 的上一级）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, ".cache")


@dataclass
class DeveloperProfile:
    """开发者账号信息。"""

    name: str = ""
    avatar_url: str = ""
    urs: str = ""
    user_id: str = ""
    real_name: str = ""
    level: str = ""

    @property
    def display_name(self) -> str:
        return self.name or "未知开发者"


async def fetch_profile(client) -> DeveloperProfile:
    """读取当前登录开发者的资料。"""
    data = await client.get_user_info()
    return DeveloperProfile(
        name=str(data.get("nickname") or data.get("nick_name") or ""),
        avatar_url=str(data.get("head_img") or ""),
        urs=str(data.get("urs") or ""),
        user_id=str(data.get("user_id") or ""),
        real_name=str(data.get("real_name") or ""),
        level=str(data.get("level") or ""),
    )


def _cache_path(url: str) -> str:
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"avatar_{digest}.img")


async def fetch_avatar(url: str, timeout: float = 15.0) -> Optional[str]:
    """下载头像并缓存到本地，返回本地文件路径；失败返回 None。"""
    if not url:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            resp = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200 or not resp.content:
            return None
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except Exception:  # noqa: BLE001  头像失败不应影响主流程
        return None


__all__ = ["DeveloperProfile", "fetch_profile", "fetch_avatar", "CACHE_DIR"]
