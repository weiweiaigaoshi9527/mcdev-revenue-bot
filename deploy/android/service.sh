#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  我的世界开发者收益 QQ 机器人 —— Android (Termux) 后台常驻管理
#
#  用法：
#      ./deploy/android/service.sh start    启动（后台）
#      ./deploy/android/service.sh stop     停止
#      ./deploy/android/service.sh restart  重启
#      ./deploy/android/service.sh status   查看状态
#      ./deploy/android/service.sh log      实时查看日志
#
#  说明：
#     Termux 无 systemd，这里用 nohup + PID 文件实现后台常驻，
#     并申请唤醒锁（termux-wake-lock）防止息屏被系统冻结。
#     如需「开机自启」，可配合 Termux:Boot 应用（见 deploy/android/README.md）
# ============================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$APP_DIR/.venv"
RUN_DIR="$APP_DIR/.run"
PID_FILE="$RUN_DIR/bot.pid"
LOG_FILE="$RUN_DIR/bot.log"

mkdir -p "$RUN_DIR"

is_running() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null
}

start_bot() {
    if is_running; then
        echo "机器人已在运行（PID $(cat "$PID_FILE")）"
        return 0
    fi
    if [ ! -x "$VENV/bin/python" ]; then
        echo "!! 未找到虚拟环境，请先执行：./deploy/android/install.sh"
        exit 1
    fi

    export PYTHONIOENCODING=utf-8
    export PYTHONUNBUFFERED=1
    export MPLBACKEND=Agg

    command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

    cd "$APP_DIR"
    nohup "$VENV/bin/python" bot_qq.py >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    sleep 2
    if is_running; then
        echo "已启动（PID $(cat "$PID_FILE")），日志：$LOG_FILE"
    else
        echo "!! 启动失败，请查看日志：$LOG_FILE"
        tail -n 20 "$LOG_FILE" 2>/dev/null || true
        exit 1
    fi
}

stop_bot() {
    if ! is_running; then
        echo "机器人未在运行"
        rm -f "$PID_FILE"
        return 0
    fi
    local pid
    pid="$(cat "$PID_FILE")"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
        is_running || break
        sleep 1
    done
    if is_running; then
        echo "进程未退出，强制结束..."
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock || true
    echo "已停止"
}

status_bot() {
    if is_running; then
        echo "运行中（PID $(cat "$PID_FILE")）"
        echo "日志：$LOG_FILE"
    else
        echo "未运行"
    fi
}

case "${1:-}" in
    start)   start_bot ;;
    stop)    stop_bot ;;
    restart) stop_bot; start_bot ;;
    status)  status_bot ;;
    log)     tail -f "$LOG_FILE" ;;
    *)
        echo "用法：$0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac
