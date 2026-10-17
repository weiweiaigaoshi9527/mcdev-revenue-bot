"""官方 QQ 机器人接入（QQ 开放平台 · qq-botpy）。

与 NapCat/OneBot 方案的区别：
- **不需要挂 QQ 客户端**，用 AppID + AppSecret 直连腾讯网关
- 被动回复不受配额限制；主动推送受平台硬限（每群每月 4 条），默认关闭
- 群聊图片需先调富媒体接口上传，再以 msg_type=7 发送

入口见项目根目录 ``bot_qq.py``。
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import botpy
from botpy import Intents
from botpy.http import Route
from botpy.message import C2CMessage, GroupMessage

from . import dispatcher
from .config import PROJECT_ROOT, settings
from .dispatcher import Reply

# 单条文本消息长度上限（官方限制较严，留足余量并分片发送）
_TEXT_CHUNK = 900
# 被动回复同一消息最多 5 条
_MAX_CHUNKS = 5

_MENTION_RE = re.compile(r"<@!?\d+>")

# 见过消息的群（openid）——主动推送需要群 openid，只能从群消息里学到
_GROUPS_FILE = Path(PROJECT_ROOT) / ".cache" / "qq_groups.json"
# 主动消息配额用量：{"month": "2026-10", "count": {"<group_openid>": 1}}
_PUSH_STATE_FILE = Path(PROJECT_ROOT) / ".cache" / "qq_push_state.json"


def _log(msg: str) -> None:
    print(f"[mcdev-qqbot] {msg}", flush=True)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"写入 {path.name} 失败：{exc}")


def remember_group(group_openid: str) -> None:
    """记录群 openid，供主动推送使用。"""
    if not group_openid:
        return
    data = _load_json(_GROUPS_FILE)
    if data.get(group_openid) != datetime.now().strftime("%Y-%m-%d"):
        data[group_openid] = datetime.now().strftime("%Y-%m-%d")
        _save_json(_GROUPS_FILE, data)


def known_groups() -> List[str]:
    return list(_load_json(_GROUPS_FILE).keys())



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
        if settings.qq_push_enabled:
            self._push_task = asyncio.create_task(self._push_scheduler())
            days = "、".join(str(d) for d in (settings.qq_push_days or []))
            hours = ",".join(str(h) for h in (settings.qq_push_hours or []))
            _log(
                f"定时推送已开启：每月 {days} 日 {hours} 时 "
                f"{settings.qq_push_minute:02d} 分"
                f"（每月 {len(settings.qq_push_days or [])} 次，平台硬限 {settings.qq_push_max_per_month} 条/群/月）"
            )
            if not known_groups():
                _log("提示：还没有记录到任何群，请先在被推送的群里 @机器人 一次")

    # ------------------------------------------------------------------
    # 群聊：@机器人 触发
    # ------------------------------------------------------------------
    async def on_group_at_message_create(self, message: GroupMessage):
        text = _strip_mention(message.content)
        openid = _sender_openid(message)
        remember_group(message.group_openid)
        _log(f"群消息 <- {text!r}（发送者 {openid}）")

        is_admin = bool(openid) and openid in (settings.qq_admins or [])
        reply = await dispatcher.handle(text, is_admin=is_admin, sender=openid)

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
        reply = await dispatcher.handle(text, is_admin=is_admin, sender=openid)

        try:
            await self._send_c2c(message, reply)
        except Exception as exc:  # noqa: BLE001
            _log(f"单聊回复失败：{exc}")

    # ------------------------------------------------------------------
    # 主动推送（受平台配额限制：群聊每群每月 4 条，默认 4 次/月）
    # ------------------------------------------------------------------
    async def _push_scheduler(self) -> None:
        """定期检查，命中「日期 + 小时 + 分钟」就推送一次。"""
        last_fired = ""
        while True:
            try:
                now = datetime.now()
                if (
                    now.day in (settings.qq_push_days or [])
                    and now.hour in (settings.qq_push_hours or [])
                    and now.minute == settings.qq_push_minute
                ):
                    key = now.strftime("%Y-%m-%d %H:%M")
                    if key != last_fired:
                        last_fired = key
                        await self._do_push()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                _log(f"定时推送异常：{exc}")
            await asyncio.sleep(20)

    def _quota_state(self) -> Dict[str, object]:
        month = datetime.now().strftime("%Y-%m")
        state = _load_json(_PUSH_STATE_FILE)
        if state.get("month") != month:
            state = {"month": month, "count": {}}
        state.setdefault("count", {})
        return state

    async def _do_push(self) -> None:
        groups = known_groups()
        if not groups:
            _log("定时推送跳过：尚未记录到任何群 openid（请先在目标群 @机器人 一次）")
            return

        quota = settings.qq_push_max_per_month
        state = self._quota_state()
        counts: Dict[str, int] = state["count"]  # type: ignore[assignment]
        reply = await dispatcher.build_push_reply(compact=True)

        for gid in groups:
            used = int(counts.get(gid, 0))
            if used >= quota:
                _log(f"群 {gid} 本月主动消息配额已用尽（{used}/{quota}），跳过")
                continue
            try:
                await self._send_group_one(gid, reply)
            except Exception as exc:  # noqa: BLE001
                _log(
                    f"推送到群 {gid} 失败：{exc}\n"
                    "        提示：平台要求群主在群设置里打开「机器人主动在群聊内发言」"
                    "（如为个人开发者账号，还需机器人已审核上架）"
                )
                continue
            counts[gid] = used + 1
            _log(f"已推送到群 {gid}（本月 {counts[gid]}/{quota} 条）")

        state["count"] = counts
        _save_json(_PUSH_STATE_FILE, state)

    async def _send_group_one(self, gid: str, reply: Reply) -> None:
        """主动消息每次只发 1 条，保证「一次推送 = 消耗 1 条配额」。"""
        if reply.image:
            media = await self._upload_group_image(gid, reply.image)
            if media:
                await self.api.post_group_message(
                    group_openid=gid, msg_type=7, media=media, msg_seq=1,
                )
                return
        text = (reply.text or "").strip()
        if len(text) > _TEXT_CHUNK:
            text = text[: _TEXT_CHUNK - 1] + "…"
        await self.api.post_group_message(
            group_openid=gid, msg_type=0, content=text, msg_seq=1,
        )

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


__all__ = ["McDevQQBot", "build_client", "known_groups", "remember_group"]
