#!/usr/bin/env bash
# 前台启动（调试用，Ctrl+C 退出；正式运行请用 systemd 服务）
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"

export PYTHONIOENCODING=utf-8
export MPLBACKEND=Agg

PY="$APP_DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "未找到虚拟环境，请先运行 deploy/linux/install.sh"
    exit 1
fi

echo "启动机器人（工作目录：$APP_DIR）"
exec "$PY" bot.py
