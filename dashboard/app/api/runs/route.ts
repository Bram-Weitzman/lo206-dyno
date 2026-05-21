import { NextResponse } from "next/server";
import { db } from "@/lib/db";

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
