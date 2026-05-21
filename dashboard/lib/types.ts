// Shared types + the raw-register -> engineering-unit conversion.
//
// The logger stores RAW register values (per logger/db_schema.sql); all unit
// conversions live here in the API layer, never in the DB. Field names and
// scaling follow simulator/modbus_map.py (the authoritative register contract).

// Engineering-unit sample as returned by the API (/api/live, /api/run/[id]).
export interface Sample {
  run_id: number;
  ts: string;
  rpm: number; // 30001 ENGINE_RPM, 1:1
  torque_ftlbs: number; // 30002 TORQUE_x10 / 10
  hp: number; // precomputed by the logger: (torque_ftlbs * rpm) / 5252
  pressure: number; // 30003 HYDRAULIC_PSI, 1:1
  cht_c: number; // 30004 HEAD_TEMP_C, 1:1 degC (NOT scaled x10)
  valve_pct: number; // 40001 VALVE_POS_CMD (% x100) / 100
  control_mode: number; // 40003: 0=manual, 1=PID, 2=sweep
  sim_status: number; // 30007: 0=stopped, 1=running, 2=fault
  limiter_active: number; // 30008: 0/1
  rpm_setpoint: number; // 40002 TARGET_RPM
}

// Run summary as returned by /api/runs.
export interface RunSummary {
  id: number;
  started_at: string;
  ended_at: string | null;
  notes: string | null;
  sample_count: number;
}

// Raw row shape as stored in the `samples` table (logger/db_schema.sql).
export interface SampleRow {
  run_id: number;
  ts: string;
  rpm: number;
  torque_x10: number;
  pressure: number;
  cht: number;
  valve_cmd: number;
  rpm_setpoint: number;
  control_mode: number;
  sim_status: number;
  limiter_active: number;
  hp: number;
}

export function rowToSample(r: SampleRow): Sample {
  return {
    run_id: r.run_id,
    ts: r.ts,
    rpm: r.rpm,
    torque_ftlbs: r.torque_x10 / 10,
    hp: r.hp,
    pressure: r.pressure,
    cht_c: r.cht,
    valve_pct: r.valve_cmd / 100,
    control_mode: r.control_mode,
    sim_status: r.sim_status,
    limiter_active: r.limiter_active,
    rpm_setpoint: r.rpm_setpoint,
  };
}

// CSV export column order (per session brief). Client-side export only.
export const CSV_COLUMNS: (keyof Sample)[] = [
  "ts",
  "rpm",
  "torque_ftlbs",
  "hp",
  "pressure",
  "cht_c",
  "valve_pct",
  "control_mode",
  "sim_status",
  "limiter_active",
];
