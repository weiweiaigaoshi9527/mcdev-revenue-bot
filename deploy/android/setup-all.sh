#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android 一键部署
#  （官方 QQ 机器人模式：无需 NapCat、无需挂 QQ 客户端）
#
#  在 Termux 中执行本脚本，即可一次完成：
#     1) 部署机器人（Python 环境 + 依赖 + .env）
#     2) 配置保活（开机自启脚本 + 打开电池优化白名单设置页）
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
echo " 我的世界开发者收益 QQ 机器人 · Android 一键部署"
echo " 模式：官方 QQ 机器人（不挂 QQ 客户端）"
echo "============================================================"
echo "项目目录：$APP_DIR"
echo

# ------------------------------------------------------------
# 步骤 1/2：机器人
# ------------------------------------------------------------
echo ">>> 步骤 1/2：部署机器人"
echo
if ! bash "$APP_DIR/deploy/android/install.sh"; then
    echo
    echo "!! 部署失败，请查看上方报错后重试。"
    exit 1
fi

# ------------------------------------------------------------
# 步骤 2/2：保活设置
# ------------------------------------------------------------
echo
echo ">>> 步骤 2/2：配置保活（开机自启 + 电池优化白名单）"
echo
bash "$APP_DIR/deploy/android/keepalive.sh" || true

# ------------------------------------------------------------
# 后续步骤
# ------------------------------------------------------------
cat <<'EOF'

============================================================
 部署完成 —— 后续 3 步
============================================================

 1) 填写配置
      nano ~/qqbot/.env
      · QQ_BOT_APPID / QQ_BOT_SECRET   （q.qq.com → 开发设置）
      · MCDEV_COOKIE                   （开发者平台 F12 复制）

    自检： ~/qqbot/.venv/bin/python ~/qqbot/tools/probe.py

 2) 前台试跑一次（确认能连上腾讯网关）
      cd ~/qqbot && ./deploy/android/start.sh
    看到「机器人已就绪」后按 Ctrl+C 停掉，转后台常驻。

 3) 启动保活守护（自动持有唤醒锁，崩溃自动重启）
      cd ~/qqbot && ./deploy/android/watchdog.sh start
      查看状态： ./deploy/android/watchdog.sh status
      实时日志： ./deploy/android/watchdog.sh log

 保活提醒：务必在系统设置里把 Termux 的电池优化设为「无限制」并允许自启动，
           否则息屏后仍可能被系统杀掉。详见 deploy/android/README.md

EOF
