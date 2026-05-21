#!/usr/bin/env bash
# Bring the LO206 dyno stack up: simulator, logger, dashboard.
# OpenPLC's systemd service + its PLC runtime are checked (and started if
# needed) so the closed loop has a controller. Each managed process is started
# with setsid so the PID file holds a process-group leader -- stop_all.sh
# signals the whole group, catching children like npm's next-server.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="/opt/dyno-venv"
SIM_PID=/tmp/dyno_sim.pid
LOG_PID=/tmp/dyno_logger.pid
DASH_PID=/tmp/dyno_dashboard.pid
SIM_LOG=/tmp/dyno_sim.log
LOG_LOG=/tmp/dyno_logger.log
DASH_LOG=/tmp/dyno_dashboard.log
OPENPLC_URL="http://localhost:8080"
OPENPLC_USER="openplc"
OPENPLC_PASS="openplc"

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

stop_if_running() {
    local label="$1" pidfile="$2"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(cat "$pidfile")
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            echo "  stopping existing $label (pid $pid)"
            kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
            for _ in 1 2 3 4 5; do
                kill -0 "$pid" 2>/dev/null || break
                sleep 1
            done
            kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
}

wait_for_port() {
    local port="$1" tries="${2:-15}"
    for _ in $(seq 1 "$tries"); do
        if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":${port}\$"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

echo "[start_all] root: $ROOT"

echo "[start_all] step 0: OpenPLC controller"
if ! systemctl is-active --quiet openplc; then
    echo "  openplc service inactive -> starting via sudo"
    sudo -n systemctl start openplc
    sleep 4
fi
if ! pgrep -f "core/openplc" >/dev/null; then
    echo "  PLC runtime not running -> starting via web API"
    JAR=$(mktemp)
    curl -s -c "$JAR" -o /dev/null "$OPENPLC_URL/login"
    curl -s -c "$JAR" -b "$JAR" -X POST -o /dev/null         -d "username=${OPENPLC_USER}&password=${OPENPLC_PASS}"         "$OPENPLC_URL/login"
    curl -s -c "$JAR" -b "$JAR" -L -o /dev/null "$OPENPLC_URL/start_plc"
    rm -f "$JAR"
    sleep 5
fi
if pgrep -f "core/openplc" >/dev/null; then
    echo "  OK PLC runtime active"
else
    echo "  WARN PLC runtime did not start; sim will run without closed-loop control"
fi

echo "[start_all] step 1: stop any existing managed processes"
stop_if_running simulator "$SIM_PID"
stop_if_running logger    "$LOG_PID"
stop_if_running dashboard "$DASH_PID"

echo "[start_all] step 2: start simulator"
cd "$ROOT"
setsid nohup "${VENV}/bin/python" simulator/modbus_server.py     > "$SIM_LOG" 2>&1 < /dev/null &
echo $! > "$SIM_PID"
if ! wait_for_port 5020 15; then
    echo "ERROR: simulator did not bind port 5020 within 15s (see $SIM_LOG)"
    exit 1
fi
echo "  simulator listening on :5020 (pid $(cat "$SIM_PID"))"

echo "[start_all] step 3: start logger"
NOTES="auto-start $(date +%Y-%m-%d\ %H:%M)"
setsid nohup "${VENV}/bin/python" logger/logger.py     --interval 100 --notes "$NOTES"     > "$LOG_LOG" 2>&1 < /dev/null &
echo $! > "$LOG_PID"
sleep 2
echo "  logger pid $(cat "$LOG_PID"), notes: $NOTES"

echo "[start_all] step 4: start dashboard"
cd "$ROOT/dashboard"
setsid nohup npm run dev > "$DASH_LOG" 2>&1 < /dev/null &
echo $! > "$DASH_PID"
cd "$ROOT"
if ! wait_for_port 3000 25; then
    echo "ERROR: dashboard did not bind port 3000 within 25s (see $DASH_LOG)"
    exit 1
fi
echo "  dashboard pid $(cat "$DASH_PID")"

echo
echo "Dashboard ready at http://localhost:3000"
