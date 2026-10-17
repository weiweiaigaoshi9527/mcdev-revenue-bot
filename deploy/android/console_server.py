"""移动端控制台后端（Termux 本地 HTTP 服务）。

给手机 App / 浏览器提供一个本地控制面板，只监听 ``127.0.0.1``，不对外暴露。

接口：
    GET  /                     控制台页面（同目录 console.html）
    GET  /api/status           机器人 / 守护 / 控制台 运行状态
    POST /api/watchdog         {"action": "start|stop|restart"}
    GET  /api/log?lines=200    机器人日志尾部
    GET  /api/env              读取 .env
    POST /api/env              {"text": "..."}  写回 .env
    POST /api/query            {"text": "收益"} → {"text": ..., "image": "base64"}

启动：
    python deploy/android/console_server.py
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(str(_ROOT / ".env"), override=False)
except Exception:  # pragma: no cover
    pass

PORT = int(os.getenv("MCDEV_CONSOLE_PORT", "8770"))
APP_DIR = _ROOT
RUN_DIR = APP_DIR / ".run"
WATCHDOG = APP_DIR / "deploy" / "android" / "watchdog.sh"
BOT_LOG = RUN_DIR / "bot.log"
WATCHDOG_LOG = RUN_DIR / "watchdog.log"
ENV_FILE = APP_DIR / ".env"
HTML_FILE = Path(__file__).resolve().parent / "console.html"

# ----------------------------------------------------------------------
# 后台事件循环：dispatcher 里的 httpx 连接池必须固定在同一个 loop 上，
# 否则会出现 "Event loop is closed"。
# ----------------------------------------------------------------------
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def run_async(coro, timeout: float = 180.0):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


# ----------------------------------------------------------------------
# 工具
# ----------------------------------------------------------------------
def _read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text().strip())
    except Exception:  # noqa: BLE001
        return None


def _alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _tail(path: Path, lines: int = 200) -> str:
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(data[-lines:])
    except Exception:  # noqa: BLE001
        return ""


def _watchdog(action: str) -> dict:
    """调用 watchdog.sh，返回 {"ok": bool, "output": str}"""
    if action not in {"start", "stop", "restart", "status"}:
        return {"ok": False, "output": "不支持的操作"}
    try:
        proc = subprocess.run(
            ["bash", str(WATCHDOG), action],
            cwd=str(APP_DIR),
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return {"ok": proc.returncode == 0, "output": out.strip()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"执行失败：{exc}"}


def _status() -> dict:
    bot_pid = _read_pid(RUN_DIR / "bot.pid")
    wd_pid = _read_pid(RUN_DIR / "watchdog.pid")
    return {
        "bot_running": _alive(bot_pid),
        "bot_pid": bot_pid,
        "watchdog_running": _alive(wd_pid),
        "watchdog_pid": wd_pid,
        "port": PORT,
        "app_dir": str(APP_DIR),
    }


# ----------------------------------------------------------------------
# HTTP 处理
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "mcdev-console"

    # 关闭默认的访问日志刷屏
    def log_message(self, fmt, *args):  # noqa: A003
        pass

    # ---------------- 基础响应 ----------------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: dict, code: int = 200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            return {}

    def _query_int(self, key: str, default: int) -> int:
        qs = parse_qs(urlparse(self.path).query)
        try:
            return max(1, min(5000, int((qs.get(key) or [default])[0])))
        except ValueError:
            return default

    # ---------------- 路由 ----------------
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path

        if path in {"/", "/index.html"}:
            try:
                html = HTML_FILE.read_bytes()
            except Exception:  # noqa: BLE001
                self._send(500, b"console.html not found", "text/plain")
                return
            self._send(200, html, "text/html")
            return

        if path == "/api/status":
            self._json(_status())
            return

        if path == "/api/log":
            lines = self._query_int("lines", 200)
            self._json(
                {
                    "bot": _tail(BOT_LOG, lines),
                    "watchdog": _tail(WATCHDOG_LOG, lines),
                }
            )
            return

        if path == "/api/env":
            try:
                text = ENV_FILE.read_text(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                text = ""
            self._json({"text": text})
            return

        self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        body = self._body()

        if path == "/api/watchdog":
            self._json(_watchdog(str(body.get("action") or "")))
            return

        if path == "/api/env":
            text = str(body.get("text") or "")
            try:
                ENV_FILE.write_text(text, encoding="utf-8")
                # 让运行中的查询接口重新加载配置
                from mcdev_bot import dispatcher
                from mcdev_bot.config import reload_settings

                reload_settings()
                dispatcher.reset_service()
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "output": f"保存失败：{exc}"}, 500)
                return
            self._json({"ok": True, "output": "已保存，新配置在下一次查询生效"})
            return

        if path == "/api/query":
            text = str(body.get("text") or "").strip()
            try:
                from mcdev_bot import dispatcher

                reply = run_async(dispatcher.handle(text))
                payload = {"text": reply.text or "", "caption": reply.caption or ""}
                if reply.image:
                    payload["image"] = base64.b64encode(reply.image).decode("ascii")
                self._json(payload)
            except Exception as exc:  # noqa: BLE001
                self._json({"text": f"查询失败：{exc}"}, 500)
            return

        self._json({"error": "not found"}, 404)


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists() and (APP_DIR / ".env.example").exists():
        ENV_FILE.write_text(
            (APP_DIR / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
        )

    # 预加载开发者昵称 / 头像（图表 logo），失败不影响启动
    try:
        from mcdev_bot import dispatcher as _d

        run_async(_d.warmup(), timeout=60)
    except Exception:  # noqa: BLE001
        pass

    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[console] 控制台已启动：http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
