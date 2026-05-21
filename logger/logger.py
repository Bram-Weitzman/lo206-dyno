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
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def start_run(conn: sqlite3.Connection, notes: str | None) -> int:
    cur = conn.execute(
        "INSERT INTO test_runs (started_at, notes) VALUES (?, ?)",
        (utc_now_iso(), notes),
    )
    conn.commit()
    return cur.lastrowid


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
    parser.add_argument("--notes", default=None, help="Optional note attached to this test run")
    args = parser.parse_args()

    interval_s = args.interval / 1000.0
    db_path = Path(args.db)

    conn = init_db(db_path)
    run_id = start_run(conn, args.notes)
    log(f"Run #{run_id} started. Logging to {db_path} at {args.interval}ms")

    client = ModbusTcpClient(args.host, port=args.port)
    client.connect()

    stop = {"flag": False}

    def handle_sigint(signum, frame):
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_sigint)

    sample_count = 0
    last_status = 0.0
    next_tick = time.monotonic()

    insert_sql = (
        "INSERT INTO samples (run_id, ts, rpm, torque_x10, pressure, cht, "
        "valve_cmd, rpm_setpoint, control_mode, safety_enable, sim_status, "
        "limiter_active, hp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    try:
        while not stop["flag"]:
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
        conn.execute("UPDATE test_runs SET ended_at = ? WHERE id = ?", (utc_now_iso(), run_id))
        conn.commit()
        log(f"Run #{run_id} ended. {sample_count} samples written.")
        conn.close()
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
