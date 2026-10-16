"""官方 QQ 机器人接入（QQ 开放平台 · qq-botpy）。

与 NapCat/OneBot 方案的区别：
- **不需要挂 QQ 客户端**，用 AppID + AppSecret 直连腾讯网关
- 只有被动回复（用户 @机器人 / 私聊才响应），不做主动推送
- 群聊图片需先调富媒体接口上传，再以 msg_type=7 发送

入口见项目根目录 ``bot_qq.py``。
"""
from __future__ import annotations

import base64
import re
from typing import List, Optional

import botpy
from botpy import Intents
from botpy.http import Route
from botpy.message import C2CMessage, GroupMessage

from . import dispatcher
from .config import settings
from .dispatcher import Reply

# 单条文本消息长度上限（官方限制较严，留足余量并分片发送）
_TEXT_CHUNK = 900
# 被动回复同一消息最多 5 条
_MAX_CHUNKS = 5

_MENTION_RE = re.compile(r"<@!?\d+>")


def _log(msg: str) -> None:
    print(f"[mcdev-qqbot] {msg}", flush=True)


def _strip_mention(text: str) -> str:
    """去掉群聊消息里的 @机器人 前缀。"""
    return _MENTION_RE.sub("", text or "").strip()


def _chunks(text: str, size: int = _TEXT_CHUNK) -> List[str]:
    """按行切分长文本，尽量不切断行。"""
    lines = (text or "").splitlines() or [""]
    out: List[str] = []
    buf = ""
    for line in lines:
        if len(line) > size:            # 超长单行硬切
            if buf:
                out.append(buf)
                buf = ""
            for i in range(0, len(line), size):
                out.append(line[i:i + size])
            continue
        if len(buf) + len(line) + 1 > size:
            out.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        out.append(buf)
    return out[:_MAX_CHUNKS] or [""]


def _sender_openid(message) -> str:
    """取发送者 openid（群聊为 member_openid，单聊为 user_openid）。"""
    author = getattr(message, "author", None)
    if author is None:
        return ""
    for key in ("member_openid", "user_openid", "union_openid", "id"):
        val = None
        if isinstance(author, dict):
            val = author.get(key)
        else:
            val = getattr(author, key, None)
        if val:
            return str(val)
    return ""


class McDevQQBot(botpy.Client):
    """官方 QQ 机器人客户端。"""

    async def on_ready(self):
        _log(f"机器人已就绪：{self.robot.name}")

    # ------------------------------------------------------------------
    # 群聊：@机器人 触发
    # ------------------------------------------------------------------
    async def on_group_at_message_create(self, message: GroupMessage):
        text = _strip_mention(message.content)
        openid = _sender_openid(message)
        _log(f"群消息 <- {text!r}（发送者 {openid}）")

        is_admin = bool(openid) and openid in (settings.qq_admins or [])
        reply = await dispatcher.handle(text, is_admin=is_admin)

        try:
            await self._send_group(message, reply)
        except Exception as exc:  # noqa: BLE001
            _log(f"群消息回复失败：{exc}")

    # ------------------------------------------------------------------
    # 单聊
    # ------------------------------------------------------------------
    async def on_c2c_message_create(self, message: C2CMessage):
        text = (message.content or "").strip()
        openid = _sender_openid(message)
        _log(f"单聊 <- {text!r}（发送者 {openid}）")

        is_admin = bool(openid) and openid in (settings.qq_admins or [])
        reply = await dispatcher.handle(text, is_admin=is_admin)

        try:
            await self._send_c2c(message, reply)
        except Exception as exc:  # noqa: BLE001
            _log(f"单聊回复失败：{exc}")

    # ------------------------------------------------------------------
    # 发送
    # ------------------------------------------------------------------
    async def _send_group(self, message: GroupMessage, reply: Reply) -> None:
        gid = message.group_openid
        seq = 1

        if reply.text:
            for chunk in _chunks(reply.text):
                await self.api.post_group_message(
                    group_openid=gid, msg_type=0, content=chunk,
                    msg_id=message.id, msg_seq=seq,
                )
                seq += 1

        if reply.image:
            media = await self._upload_group_image(gid, reply.image)
            if media:
                await self.api.post_group_message(
                    group_openid=gid, msg_type=7, media=media,
                    msg_id=message.id, msg_seq=seq,
                )
                seq += 1
                if reply.caption:
                    for chunk in _chunks(reply.caption):
                        await self.api.post_group_message(
                            group_openid=gid, msg_type=0, content=chunk,
                            msg_id=message.id, msg_seq=seq,
                        )
                        seq += 1

    async def _send_c2c(self, message: C2CMessage, reply: Reply) -> None:
        openid = _sender_openid(message)
        seq = 1

        if reply.text:
            for chunk in _chunks(reply.text):
                await self.api.post_c2c_message(
                    openid=openid, msg_type=0, content=chunk,
                    msg_id=message.id, msg_seq=seq,
                )
                seq += 1

        if reply.image:
            media = await self._upload_c2c_image(openid, reply.image)
            if media:
                await self.api.post_c2c_message(
                    openid=openid, msg_type=7, media=media,
                    msg_id=message.id, msg_seq=seq,
                )
                seq += 1
                if reply.caption:
                    for chunk in _chunks(reply.caption):
                        await self.api.post_c2c_message(
                            openid=openid, msg_type=0, content=chunk,
                            msg_id=message.id, msg_seq=seq,
                        )
                        seq += 1

    # ------------------------------------------------------------------
    # 富媒体上传（官方接口支持 file_data base64）
    # ------------------------------------------------------------------
    async def _upload_file(self, route: Route, image: bytes) -> Optional[dict]:
        payload = {
            "file_type": 1,                      # 1 = 图片 png/jpg
            "file_data": base64.b64encode(image).decode("ascii"),
            "srv_send_msg": False,               # 只上传，不直接发送
        }
        try:
            res = await self.api._http.request(route, json=payload)
        except Exception as exc:  # noqa: BLE001
            _log(f"图片上传失败：{exc}")
            return None
        if isinstance(res, dict) and res.get("file_info"):
            return {"file_info": res["file_info"]}
        _log(f"图片上传返回异常：{str(res)[:200]}")
        return None

    async def _upload_group_image(self, group_openid: str, image: bytes) -> Optional[dict]:
        route = Route("POST", "/v2/groups/{group_openid}/files", group_openid=group_openid)
        return await self._upload_file(route, image)

    async def _upload_c2c_image(self, openid: str, image: bytes) -> Optional[dict]:
        route = Route("POST", "/v2/users/{openid}/files", openid=openid)
        return await self._upload_file(route, image)


def build_client() -> McDevQQBot:
    """按配置构造客户端。"""
    intents = Intents(public_messages=True)
    return McDevQQBot(
        intents=intents,
        is_sandbox=settings.qq_sandbox,
        timeout=30,
        bot_log=False,
    )


__all__ = ["McDevQQBot", "build_client"]
