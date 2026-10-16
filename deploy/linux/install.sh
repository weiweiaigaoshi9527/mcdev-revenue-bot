#!/usr/bin/env bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Linux 一键部署
#
#  用法：
#     chmod +x deploy/linux/install.sh
#     ./deploy/linux/install.sh
#
#  作用：
#     1) 安装系统依赖（Python3 / venv / 中文字体）
#     2) 创建虚拟环境并安装 Python 依赖
#     3) 生成 .env 配置模板
#     4) 注册 systemd 服务并设为开机自启
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="mcdev-bot"
PYTHON="${PYTHON:-python3}"
VENV="$APP_DIR/.venv"

echo "============================================================"
echo " 我的世界开发者收益 QQ 机器人 · Linux 部署"
echo "============================================================"
echo "项目目录：$APP_DIR"
echo "Python  ：$($PYTHON --version 2>&1 || echo '未安装')"
echo

# ------------------------------------------------------------
# 1. 系统依赖
# ------------------------------------------------------------
echo "==> [1/4] 安装系统依赖"
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip fonts-noto-cjk
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip google-noto-sans-cjk-fonts
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y python3 python3-pip google-noto-sans-cjk-fonts
elif command -v apk >/dev/null 2>&1; then
    sudo apk add --no-cache python3 py3-pip font-noto-cjk
else
    echo "!! 未识别的包管理器，请自行确保已安装：python3 / python3-venv / 中文字体"
fi

# ------------------------------------------------------------
# 2. 虚拟环境 + Python 依赖
# ------------------------------------------------------------
echo
echo "==> [2/4] 创建虚拟环境并安装依赖"
"$PYTHON" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"
echo "依赖安装完成"

# ------------------------------------------------------------
# 3. 配置文件
# ------------------------------------------------------------
echo
echo "==> [3/4] 准备配置文件"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "已生成 .env（请填写 MCDEV_COOKIE 等配置）"
else
    echo ".env 已存在，跳过"
fi

# ------------------------------------------------------------
# 4. systemd 服务
# ------------------------------------------------------------
echo
echo "==> [4/4] 注册 systemd 服务"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__USER__|$(id -un)|g" \
    "$APP_DIR/deploy/linux/mcdev-bot.service" \
    | sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo
echo "============================================================"
echo " 部署完成"
echo "============================================================"
echo "  启动服务 ： sudo systemctl start $SERVICE_NAME"
echo "  查看状态 ： systemctl status $SERVICE_NAME"
echo "  实时日志 ： journalctl -u $SERVICE_NAME -f"
echo "  停止服务 ： sudo systemctl stop $SERVICE_NAME"
echo "  取消自启 ： sudo systemctl disable $SERVICE_NAME"
echo
echo "  自检（不启动服务）"
echo "      $VENV/bin/python tools/probe.py"
echo
echo "  QQ 接入：本项目通过 OneBot v11 反向 WebSocket 接收消息，"
echo "  请另装 OneBot 实现并指向 ws://127.0.0.1:8080/onebot/v11/ws"
echo "    · NapCat（支持 Linux）：https://napneko.github.io/"
echo "    · Lagrange.OneBot      ：https://lagrangedev.github.io/Lagrange.Doc/"
echo
