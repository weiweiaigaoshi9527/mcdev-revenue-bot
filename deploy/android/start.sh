#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android (Termux) 前台启动
#
#  用法：
#      ./deploy/android/start.sh
#
#  说明：
#     前台运行官方 QQ 机器人（bot_qq.py），日志直接打印到当前终端，Ctrl+C 退出。
#     需要后台常驻请改用 deploy/android/watchdog.sh
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$APP_DIR/.venv"

if [ ! -x "$VENV/bin/python" ]; then
    echo "!! 未找到虚拟环境，请先执行：./deploy/android/install.sh"
    exit 1
fi

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg

# 申请唤醒锁，避免息屏后进程被系统挂起
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

cd "$APP_DIR"
echo "启动官方 QQ 机器人（出站长连接，无需开放端口）..."
exec "$VENV/bin/python" bot_qq.py
