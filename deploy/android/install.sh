#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android (Termux) 一键部署
#
#  前置：
#     1) 安装 Termux（建议从 F-Droid 安装，勿用 Google Play 旧版）
#     2) 把本项目目录放到 Termux 可访问的位置，例如
#          ~/qqbot            （推荐：cp -r /sdcard/qqbot ~/qqbot）
#     3) 在 Termux 中执行：
#          chmod +x deploy/android/install.sh
#          ./deploy/android/install.sh
#
#  说明：
#     · 安卓无需 root，QQ 接入推荐用官方 NapCat.Termux（Termux 内 proot 跑
#       官方 QQ + NapCat），也可用 OpenShamrock + LSPatch 注入手机 QQ
#     · 本脚本只负责把「机器人服务端」跑起来，QQ 接入见 deploy/android/README.md
#     · matplotlib 在 Termux 上需要现场编译，可能较慢甚至失败；
#       失败时脚本会提示，机器人仍可正常运行（图表自动降级为文字）
# ============================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$APP_DIR/.venv"

echo "============================================================"
echo " 我的世界开发者收益 QQ 机器人 · Android(Termux) 部署"
echo "============================================================"
echo "项目目录：$APP_DIR"
echo

if [ ! -d "/data/data/com.termux" ]; then
    echo "!! 未检测到 Termux 环境，本脚本仅适用于 Termux。"
    echo "   （Linux 服务器请改用 deploy/linux/install.sh）"
    exit 1
fi

# ------------------------------------------------------------
# 1. 基础依赖
# ------------------------------------------------------------
echo "==> [1/5] 安装系统依赖"
pkg update -y || true
pkg install -y python python-pip git || {
    echo "!! 系统依赖安装失败，请检查网络后重试"
    exit 1
}
# 中文字体（图表用，可选）
pkg install -y fontconfig || true
# procps 提供 pgrep，供 watchdog.sh 看护 NapCat（可选）
pkg install -y procps || true

# ------------------------------------------------------------
# 2. 虚拟环境（--system-site-packages 以便复用 pkg 安装的 numpy）
# ------------------------------------------------------------
echo
echo "==> [2/5] 创建虚拟环境"
if [ ! -d "$VENV" ]; then
    python -m venv --system-site-packages "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip

# ------------------------------------------------------------
# 3. numpy（Termux 提供预编译包，避免 matplotlib 现场编译失败）
# ------------------------------------------------------------
echo
echo "==> [3/5] 安装 numpy（预编译包，可选）"
pkg install -y python-numpy || echo "  （python-numpy 安装失败，稍后由 pip 尝试）"

# ------------------------------------------------------------
# 4. Python 依赖（核心依赖必须成功，图表依赖尽力而为）
# ------------------------------------------------------------
echo
echo "==> [4/5] 安装 Python 依赖"
CORE_DEPS=(
    "nonebot2[fastapi]>=2.3.0"
    "nonebot-adapter-onebot>=2.4.0"
    "nonebot-plugin-apscheduler>=0.5.0"
    "httpx>=0.27.0"
    "python-dotenv>=1.0.0"
)
"$VENV/bin/pip" install "${CORE_DEPS[@]}" || {
    echo "!! 核心依赖安装失败，请检查网络后重试"
    exit 1
}

echo "  --> 尝试安装图表依赖 matplotlib（可能较慢）..."
if ! "$VENV/bin/pip" install --no-build-isolation "matplotlib>=3.7.0"; then
    echo "  !! matplotlib 安装失败。机器人仍可运行，但图表指令会降级为文字。"
    echo "     如确需图表：可稍后手动执行"
    echo "         pkg install -y python-numpy"
    echo "         $VENV/bin/pip install --no-build-isolation matplotlib"
    echo "     并在 .env 中确认 MCDEV_CHART_ENABLED=true"
fi

# ------------------------------------------------------------
# 5. 配置文件
# ------------------------------------------------------------
echo
echo "==> [5/5] 准备配置文件"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "已生成 .env（请填写 MCDEV_COOKIE 等配置）"
else
    echo ".env 已存在，跳过"
fi

chmod +x "$APP_DIR/deploy/android/"*.sh 2>/dev/null || true

echo
echo "============================================================"
echo " 部署完成"
echo "============================================================"
echo "  自检（校验 Cookie 与接口）"
echo "      $VENV/bin/python tools/probe.py"
echo
echo "  前台启动（调试）"
echo "      ./deploy/android/start.sh"
echo
echo "  后台常驻（保活守护：唤醒锁 + 崩溃自动重启，推荐）"
echo "      ./deploy/android/watchdog.sh start   # 启动守护"
echo "      ./deploy/android/watchdog.sh status  # 查看状态"
echo "      ./deploy/android/watchdog.sh stop    # 停止"
echo
echo "  系统侧保活设置（电池优化白名单 + 开机自启）"
echo "      ./deploy/android/keepalive.sh"
echo
echo "  QQ 接入（免 root）：推荐官方 NapCat.Termux，一键安装："
echo "      curl -o napcat.termux.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.termux.sh && bash napcat.termux.sh"
echo "  安装后在 NapCat WebUI（http://localhost:6099/webui）的「网络配置」中"
echo "  新建 WebSocket 客户端（反向），地址填："
echo "      ws://127.0.0.1:8080/onebot/v11/ws"
echo "  另一条免 root 路线：OpenShamrock + LSPatch。详见 deploy/android/README.md"
echo
