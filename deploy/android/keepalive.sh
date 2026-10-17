#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android 系统侧保活设置
#
#  作用（能自动做的部分全部自动完成）：
#     1) 写入 Termux:Boot 开机自启脚本（开机自动拉起守护）
#     2) 打开「电池优化白名单」设置页，方便你一键放行 Termux
#     3) 打开 Termux 应用详情页，方便你开启「自启动 / 后台运行」
#     4) 打印剩余需要手动确认的清单
#
#  用法：
#     ./deploy/android/keepalive.sh
# ============================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/mcdev-watchdog.sh"

echo "============================================================"
echo " 安卓保活设置"
echo "============================================================"
echo

# ------------------------------------------------------------
# 1. Termux:Boot 开机自启
# ------------------------------------------------------------
echo "==> [1/3] 写入开机自启脚本"
mkdir -p "$BOOT_DIR"
cat >"$BOOT_SCRIPT" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
# 由 mcdev-bot 的 keepalive.sh 自动生成：开机拉起保活守护
sleep 20
termux-wake-lock
cd "$APP_DIR" && ./deploy/android/watchdog.sh start
EOF
chmod +x "$BOOT_SCRIPT"
echo "已写入：$BOOT_SCRIPT"
echo "（需安装 Termux:Boot 应用后才会生效，见下方第 3 步）"
echo

# ------------------------------------------------------------
# 2. 打开系统设置页
# ------------------------------------------------------------
echo "==> [2/3] 打开系统设置页"
open_settings() {
    if command -v am >/dev/null 2>&1; then
        am start -a "$1" ${2:+-d "$2"} >/dev/null 2>&1 \
            && echo "已打开：$3" \
            || echo "无法自动打开「$3」，请手动进入设置"
    else
        echo "未找到 am 命令，请手动进入设置：$3"
    fi
    sleep 2
}

# 电池优化白名单（在列表里找到 Termux，选「不优化 / 无限制」）
open_settings android.settings.IGNORE_BATTERY_OPTIMIZATION_SETTINGS "" "电池优化白名单"
# Termux 应用详情（开启自启动 / 后台运行 / 省电策略无限制）
open_settings android.settings.APPLICATION_DETAILS_SETTINGS "package:com.termux" "Termux 应用详情"
echo

# ------------------------------------------------------------
# 3. 手动确认清单
# ------------------------------------------------------------
cat <<'EOF'
==> [3/3] 请在手机上确认以下设置

 ┌─ 必做 ────────────────────────────────────────────────┐
 │ 1. 电池优化：找到 Termux → 选择「不优化 / 无限制」      │
 │ 2. Termux 应用详情 → 省电策略 → 「无限制」             │
 │ 3. Termux 应用详情 → 允许「自启动 / 后台活动」          │
 │    （不同品牌叫法不同：自启动、允许后台运行、锁屏清理白名单）│
 │ 4. 在最近任务里给 Termux「加锁」，避免一键清理时被杀    │
 └───────────────────────────────────────────────────────┘

 ┌─ 建议 ────────────────────────────────────────────────┐
 │ · 安装 Termux:Boot（F-Droid），开机自启才会生效         │
 │     https://f-droid.org/packages/com.termux.boot/      │
 └───────────────────────────────────────────────────────┘

 设置完成后启动守护：
     ./deploy/android/watchdog.sh start
 查看状态：
     ./deploy/android/watchdog.sh status

EOF
