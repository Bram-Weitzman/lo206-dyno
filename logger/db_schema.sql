-- LO206 dyno data logger — SQLite schema.
--
-- STORAGE DECISION: raw register values, not converted engineering units.
-- Torque is stored as torque_x10 (the raw 30002 value, ft-lbs x10) and head
-- temperature as cht (the raw 30004 value). The dashboard / analysis layer does
-- the display conversion (torque_x10 / 10.0). Storing the raw integers preserves
-- the exact value that crossed the Modbus wire at full resolution and avoids
-- baking a float rounding step into the durable record. The one computed column
-- we DO store is hp, because it is derived from two registers and is convenient
-- to have precomputed for plotting power curves.
--
-- CONTRACT NOTE: column scaling follows simulator/modbus_map.py + plc/register_map.md.
--   cht (30004 HEAD_TEMP_C) is 1:1 degrees C, NOT scaled x10 — do not divide it.
--   sim_status is read from 30007 (30006 is the reserved AFR register).

CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,   -- ISO-8601 UTC
    ended_at    TEXT,            -- NULL until the run stops cleanly
    notes       TEXT             -- optional operator note
);

CREATE TABLE IF NOT EXISTS samples (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES test_runs(id),
    ts             TEXT NOT NULL,    -- ISO-8601 UTC, millisecond precision
    rpm            INTEGER,          -- raw 30001 ENGINE_RPM (1:1)
    torque_x10     INTEGER,          -- raw 30002 TORQUE_FTLBS_x10 (divide by 10 for ft-lbs)
    pressure       INTEGER,          -- raw 30003 HYDRAULIC_PSI (1:1)
    cht            INTEGER,          -- raw 30004 HEAD_TEMP_C (deg C, 1:1 — NOT scaled)
    valve_cmd      INTEGER,          -- raw 40001 VALVE_POSITION_CMD (% x100, 0-10000)
    rpm_setpoint   INTEGER,          -- raw 40002 TARGET_RPM
    control_mode   INTEGER,          -- 40003 (0=manual, 1=PID, 2=sweep)
    safety_enable  INTEGER,          -- 40004 (0=estop, 1=run)
    sim_status     INTEGER,          -- raw 30007 SIM_STATUS (0=stopped, 1=running, 2=fault)
    limiter_active INTEGER,          -- raw 30008 LIMITER_ACTIVE (0/1)
    hp             REAL              -- computed: (torque_x10 / 10.0 * rpm) / 5252.0
);

CREATE INDEX IF NOT EXISTS idx_samples_run_ts ON samples (run_id, ts);
