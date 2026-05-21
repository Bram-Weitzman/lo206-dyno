#!/usr/bin/env bash
# Stop the LO206 dyno stack. Kills ALL processes matching each service's
# commandline pattern -- not just the pid recorded in /tmp/dyno_*.pid --
# so orphan duplicates (e.g. started by scripts/start_sim.sh or a manual
# `python3 logger/logger.py`) are also cleaned up. This is the second
# half of the idempotency fix in start_all.sh.
# Logger gets SIGINT so it stamps ended_at on its run row; sim/dashboard
# get SIGTERM. OpenPLC's systemd service is left running -- it's a system
# service, not part of this demo's lifecycle.
set -u

SIM_PID=/tmp/dyno_sim.pid
LOG_PID=/tmp/dyno_logger.pid
DASH_PID=/tmp/dyno_dashboard.pid

SIM_PATTERN='modbus_server.py'
LOG_PATTERN='logger/logger.py'
DASH_PATTERN='next dev|next-server'

# Send signal to every pid matching the cmdline pattern. We resolve pids
# fresh from pgrep (not from the pidfile) so duplicate / orphan instances
# are caught. Managed instances are setsid process-group leaders, so we
# try kill -SIG -PID (whole group) first and fall back to kill -SIG PID.
stop_all_matching() {
    local label="$1" pattern="$2" signal="$3"
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [[ -z "$pids" ]]; then
        echo "  $label: not running"
        return
    fi
    echo "  $label: sending $signal to pids $(echo "$pids" | tr '\n' ' ')"
    for pid in $pids; do
        kill -"$signal" -"$pid" 2>/dev/null || kill -"$signal" "$pid" 2>/dev/null || true
    done
    for _ in 1 2 3 4 5 6 7 8; do
        pids=$(pgrep -f "$pattern" 2>/dev/null || true)
        [[ -z "$pids" ]] && break
        sleep 1
    done
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "  $label still alive (pids $pids) -> SIGKILL"
        for pid in $pids; do
            kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        done
    fi
    echo "  $label: stopped"
}

echo "[stop_all] stopping logger (SIGINT so ended_at is stamped)"
stop_all_matching logger    "$LOG_PATTERN" INT
echo "[stop_all] stopping dashboard"
stop_all_matching dashboard "$DASH_PATTERN" TERM
echo "[stop_all] stopping simulator"
stop_all_matching simulator "$SIM_PATTERN" TERM

rm -f "$SIM_PID" "$LOG_PID" "$DASH_PID"

echo "All dyno processes stopped."
