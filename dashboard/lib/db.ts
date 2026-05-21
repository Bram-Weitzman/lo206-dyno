import path from "node:path";
import Database from "better-sqlite3";

// DB path comes from the DYNO_DB_PATH environment variable. The default assumes
// the dashboard is run from the dashboard/ directory (e.g. `npm run dev` in
// dashboard/), so data/dyno.db sits one level up. Adjust for deployment.
const DB_PATH =
  process.env.DYNO_DB_PATH ??
  path.join(process.cwd(), "..", "data", "dyno.db");

// Column list selected by the API routes — the raw `samples` columns, mapped to
// engineering units by rowToSample() in lib/types.ts.
export const SAMPLE_COLS =
  "run_id, ts, rpm, torque_x10, pressure, cht, valve_cmd, rpm_setpoint, " +
  "control_mode, sim_status, limiter_active, hp";

// Cache the connection across dev hot-reloads (module re-eval) and across
// requests in production.
const g = globalThis as unknown as { __dynoDb?: Database.Database };

export function db(): Database.Database {
  if (!g.__dynoDb) {
    // Read-only: the dashboard is a pure observer of the DB the logger writes.
    const conn = new Database(DB_PATH, {
      readonly: true,
      fileMustExist: true,
    });
    // The logger commits frequently; wait briefly for a momentary write lock
    // rather than erroring out on SQLITE_BUSY.
    conn.pragma("busy_timeout = 3000");
    g.__dynoDb = conn;
  }
  return g.__dynoDb;
}
