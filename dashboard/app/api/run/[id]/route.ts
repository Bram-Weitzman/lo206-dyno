import { NextRequest, NextResponse } from "next/server";
import { db, dbWrite, nowIso, SAMPLE_COLS } from "@/lib/db";
import { rowToSample, SampleRow } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// GET /api/run/[id]
// All samples for a run, ordered ts ASC. Same shape as /api/live, as an array.
// Used by the history chart and CSV export.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const rows = db()
    .prepare(
      `SELECT ${SAMPLE_COLS} FROM samples WHERE run_id = ? ORDER BY ts ASC, id ASC`
    )
    .all(runId) as SampleRow[];

  return NextResponse.json(rows.map(rowToSample));
}

// PATCH /api/run/[id]
// End (close) a run by stamping ended_at. Guarded so it only closes a run that
// is currently open. Ending a run is INDEPENDENT of stopping the engine (that is
// /api/command stop) -- the operator may do either without the other.
export async function PATCH(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const runId = Number(id);
  if (!Number.isFinite(runId)) {
    return NextResponse.json({ error: "invalid run id" }, { status: 400 });
  }

  const ended_at = nowIso();
  const info = dbWrite()
    .prepare("UPDATE test_runs SET ended_at = ? WHERE id = ? AND ended_at IS NULL")
    .run(ended_at, runId);

  if (info.changes === 0) {
    return NextResponse.json(
      { error: "run not found or already ended" },
      { status: 409 },
    );
  }
  return NextResponse.json({ id: runId, ended_at });
}
