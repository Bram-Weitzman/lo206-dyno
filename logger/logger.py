#!/usr/bin/env python3
"""LO206 dyno data logger.

Standalone process that polls the Modbus registers exposed by the simulator
(or, later, the real hardware I/O) and writes timestamped samples to SQLite.
It is deliberately a separate process from the simulator and the PLC: the sim
models the engine, the PLC closes the control loop, and this logger is a
passive *observer* of the register contract. It only reads telemetry and writes
its own DB — it never writes the holding (command) registers, which the PLC
owns.

Register addresses, scaling, and mode constants come from the single source of
truth, simulator/modbus_map.py, so this logger can never drift from the
contract documented in plc/register_map.md.
"""

import argparse
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pymodbus.client import ModbusTcpClient

# The Modbus register contract lives in simulator/modbus_map.py. Import it so
# there are no magic addresses/scales here — the logger reads the same map the
# simulator and PLC are built against.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "simulator"))
import modbus_map as reg  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "db_schema.sql"

_MODE_LABELS = {reg.MODE_MANUAL: "manual", reg.MODE_PID: "PID", reg.MODE_SWEEP: "sweep"}
_STATUS_LABELS = {
    reg.STATUS_STOPPED: "stopped",
    reg.STATUS_RUNNING: "running",
    reg.STATUS_FAULT: "fault",
}


def utc_now_iso() -> str:
    """ISO-8601 UTC with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    # The dashboard writes test_runs from another process; wait briefly on a
    # momentary write lock rather than erroring out on SQLITE_BUSY.
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def newest_open_run(conn: sqlite3.Connection) -> int | None:
    """ID of the newest run the dashboard has opened and not yet ended.

    The dashboard is the sole creator/closer of test_runs rows; the logger only
    reads this to learn which run to attach its samples to.
    """
    row = conn.execute(
        "SELECT id FROM test_runs WHERE ended_at IS NULL "
        "ORDER BY started_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def compute_hp(torque_x10: int, rpm: int) -> float:
    return (torque_x10 / 10.0 * rpm) / 5252.0


def main() -> int:
    parser = argparse.ArgumentParser(description="LO206 dyno Modbus -> SQLite data logger.")
    # SIM <-> REAL HARDWARE: --host and --port are the ONLY things that change
    # when this logger is pointed at the real rig instead of the simulator. The
    # register map and everything downstream stay identical (that is the whole
    # point of the contract). The sim listens on 5020 when unprivileged.
    parser.add_argument("--host", default="localhost", help="Modbus TCP host")
    parser.add_argument("--port", type=int, default=5020, help="Modbus TCP port")
    parser.add_argument("--interval", type=int, default=100, help="Poll interval in ms")
    parser.add_argument("--db", default="data/dyno.db", help="Path to SQLite file")
    # --notes is accepted for CLI/start_all.sh compatibility but is now a no-op:
    # the dashboard owns run metadata (it creates the test_runs row, notes and all).
    parser.add_argument("--notes", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    interval_s = args.interval / 1000.0
    db_path = Path(args.db)

    conn = init_db(db_path)
    log(f"Logging to {db_path} at {args.interval}ms.")

    client = ModbusTcpClient(args.host, port=args.port)
    client.connect()

    stop = {"flag": False}

    def handle_sigint(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_sigint)

    # Run lifecycle is owned by the dashboard: it INSERTs a test_runs row on
    # "start" and stamps ended_at on "end run". The logger no longer creates or
    # closes runs -- it polls for the newest open run, attaches samples to it,
    # and returns to waiting when that run is closed (no restart needed).
    run_id = None
    sample_count = 0
    last_status = 0.0
    last_run_check = -1e9    # force an immediate run check on the first iteration
    last_waiting_log = -1e9  # force an immediate "waiting" log if no run is open
    next_tick = time.monotonic()

    insert_sql = (
        "INSERT INTO samples (run_id, ts, rpm, torque_x10, pressure, cht, "
        "valve_cmd, rpm_setpoint, control_mode, safety_enable, sim_status, "
        "limiter_active, hp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    try:
        while not stop["flag"]:
            now = time.monotonic()

            # Attach to whichever run the dashboard currently has open. Re-check
            # ~1x/s (and immediately while unattached) so we notice the run being
            # closed and the next run opened without needing a restart.
            if run_id is None or now - last_run_check >= 1.0:
                last_run_check = now
                open_id = newest_open_run(conn)
                if open_id != run_id:
                    if open_id is None:
                        log(f"Run #{run_id} closed ({sample_count} samples). "
                            f"Waiting for an open run.")
                    else:
                        if run_id is not None:
                            log(f"Run #{run_id} closed ({sample_count} samples).")
                        sample_count = 0
                        last_status = 0.0
                        log(f"Attached to open run #{open_id}.")
                    run_id = open_id

            if run_id is None:
                if now - last_waiting_log >= 15.0:
                    last_waiting_log = now
                    log("Waiting for an open run.")
                time.sleep(0.5)
                next_tick = time.monotonic()
                continue

            next_tick += interval_s

            try:
                if not client.connected:
                    client.connect()

                ir = client.read_input_registers(
                    0, count=reg.INPUT_REGISTER_COUNT, device_id=reg.UNIT_ID
                )
                hr = client.read_holding_registers(
                    0, count=reg.HOLDING_REGISTER_COUNT, device_id=reg.UNIT_ID
                )
                if ir.isError() or hr.isError():
                    raise IOError(f"modbus read error: ir={ir}, hr={hr}")

                i = ir.registers
                h = hr.registers

                rpm = i[reg.IR_ENGINE_RPM]
                torque_x10 = i[reg.IR_TORQUE_X10]
                pressure = i[reg.IR_HYDRAULIC_PSI]
                cht = i[reg.IR_HEAD_TEMP_C]
                sim_status = i[reg.IR_SIM_STATUS]
                limiter_active = i[reg.IR_LIMITER_ACTIVE]

                valve_cmd = h[reg.HR_VALVE_POS_CMD]
                rpm_setpoint = h[reg.HR_TARGET_RPM]
                control_mode = h[reg.HR_CONTROL_MODE]
                safety_enable = h[reg.HR_SAFETY_ENABLE]

                hp = compute_hp(torque_x10, rpm)

                try:
                    conn.execute(
                        insert_sql,
                        (
                            run_id, utc_now_iso(), rpm, torque_x10, pressure, cht,
                            valve_cmd, rpm_setpoint, control_mode, safety_enable,
                            sim_status, limiter_active, hp,
                        ),
                    )
                    conn.commit()
                    sample_count += 1
                except sqlite3.Error as exc:
                    log(f"DB write failed (continuing): {exc}")

                now = time.monotonic()
                if now - last_status >= 1.0:
                    last_status = now
                    log(
                        f"RPM: {rpm} | Torque: {torque_x10 / 10.0:.1f} ft-lbs | "
                        f"HP: {hp:.2f} | Valve: {valve_cmd / 100.0:.1f}% | "
                        f"Mode: {_MODE_LABELS.get(control_mode, control_mode)} | "
                        f"Status: {_STATUS_LABELS.get(sim_status, sim_status)}"
                    )

            except Exception as exc:
                log(f"Poll failed: {exc}. Reconnecting in 1s.")
                client.close()
                time.sleep(1.0)
                client.connect()
                next_tick = time.monotonic()
                continue

            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                # Fell behind; resync the schedule so we don't spin.
                next_tick = time.monotonic()

    finally:
        # The logger does NOT close runs -- the dashboard owns ended_at. Just
        # release resources; the open run (if any) stays open for the next logger.
        if run_id is not None:
            log(f"Logger stopping while attached to run #{run_id} "
                f"({sample_count} samples this run).")
        else:
            log("Logger stopping (no run attached).")
        conn.close()
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
