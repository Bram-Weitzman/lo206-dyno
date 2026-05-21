#!/usr/bin/env bash
# Bring the LO206 dyno stack up: simulator, logger, dashboard.
# Idempotent: each service is gated on pgrep -f <cmdline pattern>. Re-runs
# do NOT spawn duplicates -- if a matching process already exists, its pid
# is recorded into the pidfile so stop_all.sh can clean it up later.
# OpenPLC's systemd service + its PLC runtime are checked (and started if
# needed) so the closed loop has a controller. Managed processes are
# launched with setsid so the pidfile holds a process-group leader --
# stop_all.sh signals the whole group, catching children like npm's
# next-server.
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

# Cmdline patterns used by pgrep -f to identify running instances. Loose
# enough to catch processes spawned outside this script (e.g.
# scripts/start_sim.sh, manual python3 invocations).
SIM_PATTERN='modbus_server.py'
LOG_PATTERN='logger/logger.py'
DASH_PATTERN='next dev|next-server'

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

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

# already_running label pattern pidfile
# Returns 0 if at least one process matches the pattern (and writes the
# first matching pid into the pidfile so stop_all can find it later).
# Returns 1 if nothing matches -- caller should spawn.
already_running() {
    local label="$1" pattern="$2" pidfile="$3"
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "  $label already running (pid $(echo "$pids" | tr '\n' ' ')); skipping spawn"
        echo "$pids" | head -n1 > "$pidfile"
        return 0
    fi
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
    curl -s -c "$JAR" -b "$JAR" -X POST -o /dev/null \
        -d "username=${OPENPLC_USER}&password=${OPENPLC_PASS}" \
        "$OPENPLC_URL/login"
    curl -s -c "$JAR" -b "$JAR" -L -o /dev/null "$OPENPLC_URL/start_plc"
    rm -f "$JAR"
    sleep 5
fi
if pgrep -f "core/openplc" >/dev/null; then
    echo "  OK PLC runtime active"
else
    echo "  WARN PLC runtime did not start; sim will run without closed-loop control"
fi

echo "[start_all] step 1: simulator"
if ! already_running simulator "$SIM_PATTERN" "$SIM_PID"; then
    cd "$ROOT"
    setsid nohup "${VENV}/bin/python" simulator/modbus_server.py \
        > "$SIM_LOG" 2>&1 < /dev/null &
    echo $! > "$SIM_PID"
    if ! wait_for_port 5020 15; then
        echo "ERROR: simulator did not bind port 5020 within 15s (see $SIM_LOG)"
        exit 1
    fi
    echo "  simulator listening on :5020 (pid $(cat "$SIM_PID"))"
fi

echo "[start_all] step 2: logger"
if ! already_running logger "$LOG_PATTERN" "$LOG_PID"; then
    cd "$ROOT"
    NOTES="auto-start $(date +%Y-%m-%d\ %H:%M)"
    setsid nohup "${VENV}/bin/python" logger/logger.py \
        --interval 100 --notes "$NOTES" \
        > "$LOG_LOG" 2>&1 < /dev/null &
    echo $! > "$LOG_PID"
    sleep 2
    echo "  logger pid $(cat "$LOG_PID"), notes: $NOTES"
fi

echo "[start_all] step 3: dashboard"
if ! already_running dashboard "$DASH_PATTERN" "$DASH_PID"; then
    cd "$ROOT/dashboard"
    setsid nohup npm run dev > "$DASH_LOG" 2>&1 < /dev/null &
    echo $! > "$DASH_PID"
    cd "$ROOT"
    if ! wait_for_port 3000 25; then
        echo "ERROR: dashboard did not bind port 3000 within 25s (see $DASH_LOG)"
        exit 1
    fi
    echo "  dashboard pid $(cat "$DASH_PID")"
fi

echo
echo "Dashboard ready at http://localhost:3000"
