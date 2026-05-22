import { NextRequest, NextResponse } from "next/server";
import { db, dbWrite, nowIso } from "@/lib/db";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// GET /api/runs
// All test runs, newest first, with sample_count via a LEFT JOIN (so runs with
// zero samples still appear).
export async function GET() {
  const rows = db()
    .prepare(
      `SELECT t.id, t.started_at, t.ended_at, t.notes, COUNT(s.id) AS sample_count
       FROM test_runs t
       LEFT JOIN samples s ON s.run_id = t.id
       GROUP BY t.id
       ORDER BY t.started_at DESC, t.id DESC`
    )
    .all();
  return NextResponse.json(rows);
}

// POST /api/runs
// Create (open) a new test run. The dashboard is the SOLE creator of run rows;
// the logger attaches to whatever run is currently open. Body: optional { notes }.
export async function POST(req: NextRequest) {
  let notes: string | null = null;
  try {
    const body = await req.json();
    if (body && typeof body.notes === "string") notes = body.notes;
  } catch {
    // empty / non-JSON body is fine -- notes is optional
  }

  const started_at = nowIso();
  const info = dbWrite()
    .prepare("INSERT INTO test_runs (started_at, notes) VALUES (?, ?)")
    .run(started_at, notes);

  return NextResponse.json(
    { id: Number(info.lastInsertRowid), started_at, ended_at: null, notes },
    { status: 201 },
  );
}
