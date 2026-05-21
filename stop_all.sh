#!/usr/bin/env bash
# Stop the LO206 dyno stack by consuming the PID files start_all.sh wrote.
# Logger gets SIGINT (so it stamps ended_at on the run); sim/dashboard get SIGTERM.
# OpenPLC's systemd service is left running -- it's a system service, not part
# of this demo's lifecycle.
set -u

SIM_PID=/tmp/dyno_sim.pid
LOG_PID=/tmp/dyno_logger.pid
DASH_PID=/tmp/dyno_dashboard.pid

stop_one() {
    local label="$1" pidfile="$2" signal="$3"
    if [[ ! -f "$pidfile" ]]; then
        echo "  $label: no pidfile"
        return
    fi
    local pid
    pid=$(cat "$pidfile")
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
        echo "  $label: not running (stale pidfile)"
        rm -f "$pidfile"
        return
    fi
    # Each managed process was spawned with setsid so the PID is its own
    # process-group leader. Signal the whole group (negative PID) to catch
    # children like npm's next-server worker that survive a single-PID kill.
    echo "  $label (pid $pid): sending $signal to process group"
    kill -"$signal" -"$pid" 2>/dev/null || kill -"$signal" "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "  $label still alive -> SIGKILL group"
        kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pidfile"
    echo "  $label: stopped"
}

echo "[stop_all] stopping logger (SIGINT so ended_at is stamped)"
stop_one logger    "$LOG_PID" INT
echo "[stop_all] stopping dashboard"
stop_one dashboard "$DASH_PID" TERM
echo "[stop_all] stopping simulator"
stop_one simulator "$SIM_PID" TERM

echo "All dyno processes stopped."
