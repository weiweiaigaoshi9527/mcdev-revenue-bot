#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android 一键部署（方案 A · 免 root）
#
#  在 Termux 中执行本脚本，即可一次完成：
#     1) 部署机器人服务端（Python 环境 + 依赖 + .env）
#     2) 安装官方 NapCat.Termux（proot 跑官方 QQ + NapCat，无需 root）
#     3) 配置保活（开机自启脚本 + 打开电池优化白名单设置页）
#
#  用法：
#     chmod +x deploy/android/setup-all.sh
#     ./deploy/android/setup-all.sh
#
#  装完后见脚本结尾的「后续 3 步」。
# ============================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [ ! -d "/data/data/com.termux" ]; then
    echo "!! 未检测到 Termux 环境，本脚本仅适用于 Termux。"
    exit 1
fi

echo "============================================================"
echo " 我的世界开发者收益 QQ 机器人 · Android 一键部署（免 root）"
echo "============================================================"
echo "项目目录：$APP_DIR"
echo

# ------------------------------------------------------------
# 步骤 1/3：机器人服务端
# ------------------------------------------------------------
echo ">>> 步骤 1/3：部署机器人服务端"
echo
if ! bash "$APP_DIR/deploy/android/install.sh"; then
    echo
    echo "!! 机器人服务端部署失败，请查看上方报错后重试。"
    exit 1
fi

# ------------------------------------------------------------
# 步骤 2/3：NapCat.Termux
# ------------------------------------------------------------
echo
echo ">>> 步骤 2/3：安装 NapCat.Termux（免 root）"
echo
if command -v napcat >/dev/null 2>&1; then
    echo "已检测到 napcat，跳过安装。"
else
    echo "正在下载官方安装脚本（会拉取 proot 环境 + 官方 QQ + NapCat，耗时较长）..."
    if curl -o "$HOME/napcat.termux.sh" \
        https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.termux.sh \
        && bash "$HOME/napcat.termux.sh"; then
        echo "NapCat 安装完成。"
    else
        echo
        echo "!! NapCat 安装未成功（多为网络问题）。"
        echo "   可稍后手动重试："
        echo "     curl -o napcat.termux.sh https://nclatest.znin.net/NapNeko/NapCat-Installer/main/script/install.termux.sh && bash napcat.termux.sh"
    fi
fi

# ------------------------------------------------------------
# 步骤 3/3：保活设置
# ------------------------------------------------------------
echo
echo ">>> 步骤 3/3：配置保活（开机自启 + 电池优化白名单）"
echo
bash "$APP_DIR/deploy/android/keepalive.sh" || true

# ------------------------------------------------------------
# 后续步骤
# ------------------------------------------------------------
cat <<'EOF'

============================================================
 部署完成 —— 后续 3 步
============================================================

 1) 填写开发者 Cookie
      nano ~/qqbot/.env        # 找到 MCDEV_COOKIE= 粘贴完整 Cookie 后保存
      自检： ~/qqbot/.venv/bin/python ~/qqbot/tools/probe.py

 2) 启动保活守护（自动持有唤醒锁，崩溃自动重启）
      cd ~/qqbot && ./deploy/android/watchdog.sh start
      查看状态： ./deploy/android/watchdog.sh status
      查看日志： ./deploy/android/watchdog.sh log

 3) 启动 NapCat 并登录
      napcat start 你的机器人QQ号        # 启动
      napcat log   你的机器人QQ号        # 看日志/二维码
      二维码可用「截屏 → QQ 扫一扫 → 相册」识别，或用另一台设备扫。

      然后在浏览器打开 http://localhost:6099/webui 登录 NapCat，
      在「网络配置」新建 WebSocket 客户端（反向），URL 填：
          ws://127.0.0.1:8080/onebot/v11/ws
      消息格式选 Array，保存并启用。

 保活提醒：务必在系统设置里把 Termux 的电池优化设为「无限制」并允许自启动，
           否则息屏后仍可能被系统杀掉。详见 deploy/android/README.md

EOF
