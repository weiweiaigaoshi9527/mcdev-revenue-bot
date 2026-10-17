#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android 保活守护（watchdog）
#
#  作用：
#     · 持有 Termux 唤醒锁，避免息屏后 CPU 休眠导致断线
#     · 周期性检查机器人进程，崩溃/被系统杀掉后自动拉起
#
#  用法：
#     ./deploy/android/watchdog.sh start    启动守护
#     ./deploy/android/watchdog.sh stop     停止守护（连同机器人）
#     ./deploy/android/watchdog.sh restart  重启守护
#     ./deploy/android/watchdog.sh status   查看状态
#     ./deploy/android/watchdog.sh log      实时查看守护日志
#
#  可选环境变量（写进 .env 或直接 export）：
#     MCDEV_WATCHDOG_INTERVAL=30     检查间隔（秒）
#
#  注意：本脚本与 service.sh 都管理同一个 bot.pid，二者请勿同时运行。
# ============================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$APP_DIR/.venv"
RUN_DIR="$APP_DIR/.run"
PID_FILE="$RUN_DIR/watchdog.pid"
BOT_PID_FILE="$RUN_DIR/bot.pid"
LOG_FILE="$RUN_DIR/watchdog.log"
BOT_LOG="$RUN_DIR/bot.log"

# 从 .env 读取单个键（只取需要的键，不执行文件内容，避免误执行）
_env_get() {
    [ -f "$APP_DIR/.env" ] || return 0
    local v
    v="$(grep -E "^[[:space:]]*$1=" "$APP_DIR/.env" 2>/dev/null | tail -n 1 | cut -d= -f2-)"
    v="${v%$'\r'}"          # 兼容 Windows 换行
    v="${v%\"}"; v="${v#\"}"
    v="${v%\'}"; v="${v#\'}"
    printf '%s' "$v"
}

# 优先取环境变量，其次取 .env
CHECK_INTERVAL="${MCDEV_WATCHDOG_INTERVAL:-$(_env_get MCDEV_WATCHDOG_INTERVAL)}"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"

mkdir -p "$RUN_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG_FILE"; }

# ------------------------------------------------------------
# 进程状态
# ------------------------------------------------------------
_bot_pid() { cat "$BOT_PID_FILE" 2>/dev/null || true; }

bot_alive() {
    local p
    p="$(_bot_pid)"
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

watchdog_alive() {
    [ -f "$PID_FILE" ] || return 1
    local p
    p="$(cat "$PID_FILE" 2>/dev/null || true)"
    [ -n "$p" ] && kill -0 "$p" 2>/dev/null
}

# ------------------------------------------------------------
# 启停机器人
# ------------------------------------------------------------
start_bot() {
    if [ ! -x "$VENV/bin/python" ]; then
        log "!! 未找到虚拟环境，无法启动机器人（请先跑 install.sh）"
        return 1
    fi
    export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
    cd "$APP_DIR" || return 1
    nohup "$VENV/bin/python" bot_qq.py >>"$BOT_LOG" 2>&1 &
    echo $! >"$BOT_PID_FILE"
    log "已拉起机器人，PID $!"
}

stop_bot() {
    local p
    p="$(_bot_pid)"
    if [ -n "$p" ]; then
        kill "$p" 2>/dev/null || true
        sleep 1
        kill -9 "$p" 2>/dev/null || true
        log "已停止机器人，PID $p"
    fi
    rm -f "$BOT_PID_FILE"
}

# ------------------------------------------------------------
# 守护主循环（内部使用：watchdog.sh run）
# ------------------------------------------------------------
run_loop() {
    echo $$ >"$PID_FILE"

    # 持有唤醒锁：这是安卓上最关键的一步
    if command -v termux-wake-lock >/dev/null 2>&1; then
        termux-wake-lock && log "已获取 Termux 唤醒锁"
    else
        log "!! 未找到 termux-wake-lock，请确认使用官方 Termux"
    fi

    trap 'log "守护退出"; rm -f "$PID_FILE"; command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock; exit 0' TERM INT

    log "守护启动（检查间隔 ${CHECK_INTERVAL}s）"

    while true; do
        if ! bot_alive; then
            log "机器人未运行，正在拉起..."
            start_bot
        fi

        sleep "$CHECK_INTERVAL"
    done
}

# ------------------------------------------------------------
# 对外命令
# ------------------------------------------------------------
do_start() {
    if watchdog_alive; then
        echo "守护已在运行（PID $(cat "$PID_FILE")）"
        return 0
    fi
    if [ ! -x "$VENV/bin/python" ]; then
        echo "!! 未找到虚拟环境，请先执行：./deploy/android/install.sh"
        exit 1
    fi

    # 若 service.sh 起的机器人在跑，先接管（避免双份）
    if bot_alive; then
        echo "检测到已有机器人进程，交由守护接管（不重启）"
    fi

    nohup bash "$0" run >>"$LOG_FILE" 2>&1 &
    sleep 2
    if watchdog_alive; then
        echo "守护已启动（PID $(cat "$PID_FILE")）"
        echo "日志：$LOG_FILE"
        echo "提示：请把 Termux 的电池优化设为「无限制」，见 ./deploy/android/keepalive.sh"
    else
        echo "!! 守护启动失败，请查看日志：$LOG_FILE"
        tail -n 20 "$LOG_FILE" 2>/dev/null || true
        exit 1
    fi
}

do_stop() {
    if watchdog_alive; then
        local p
        p="$(cat "$PID_FILE")"
        kill "$p" 2>/dev/null || true
        for _ in $(seq 1 10); do
            watchdog_alive || break
            sleep 1
        done
        watchdog_alive && kill -9 "$p" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    stop_bot
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock || true
    echo "守护与机器人均已停止"
}

do_status() {
    if watchdog_alive; then
        echo "守护：运行中（PID $(cat "$PID_FILE")）"
    else
        echo "守护：未运行"
    fi
    if bot_alive; then
        echo "机器人：运行中（PID $(_bot_pid)）"
    else
        echo "机器人：未运行"
    fi
    echo "日志：$LOG_FILE"
}

case "${1:-}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; do_start ;;
    status)  do_status ;;
    log)     tail -f "$LOG_FILE" ;;
    run)     run_loop ;;   # 内部：前台运行守护循环
    *)
        echo "用法：$0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac
