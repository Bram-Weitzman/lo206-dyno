import { NextRequest, NextResponse } from "next/server";
import { db, SAMPLE_COLS } from "@/lib/db";
import { rowToSample, SampleRow } from "@/lib/types";

// DESIGN DECISION — SQLite as the handoff layer.
// The logger process polls Modbus and writes data/dyno.db continuously. This
// dashboard reads from the same file. There is no shared in-memory state, no
// message bus, no IPC — just SQLite. This intentionally keeps the logger and the
// dashboard fully decoupled: either can be restarted independently, and nothing
// here talks to Modbus directly (that is the logger's job). The same code reads
// the sim today or real hardware tomorrow — only the logger's --host/--port move.

export const runtime = "nodejs"; // better-sqlite3 is a native module
export const dynamic = "force-dynamic"; // always read the live DB, never cache

// GET /api/live?run_id=N
// Most recent sample for run N (or the most recent run if run_id is omitted).
export async function GET(req: NextRequest) {
  const d = db();
  const param = req.nextUrl.searchParams.get("run_id");
  let runId: number;

  if (param === null) {
    const latest = d
      .prepare(
        "SELECT id FROM test_runs ORDER BY started_at DESC, id DESC LIMIT 1"
      )
      .get() as { id: number } | undefined;
    if (!latest) return NextResponse.json(null);
    runId = latest.id;
  } else {
    runId = Number(param);
    if (!Number.isFinite(runId)) {
      return NextResponse.json({ error: "invalid run_id" }, { status: 400 });
    }
  }

  const row = d
    .prepare(
      `SELECT ${SAMPLE_COLS} FROM samples WHERE run_id = ? ORDER BY ts DESC, id DESC LIMIT 1`
    )
    .get(runId) as SampleRow | undefined;

  if (!row) return NextResponse.json(null);
  return NextResponse.json(rowToSample(row));
}
