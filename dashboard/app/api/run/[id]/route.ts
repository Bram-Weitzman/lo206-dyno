import { NextRequest, NextResponse } from "next/server";
import { db, SAMPLE_COLS } from "@/lib/db";
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
