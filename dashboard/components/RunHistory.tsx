"use client";

import { useEffect, useState } from "react";
import LiveChart, { ChartPoint } from "@/components/LiveChart";
import { CSV_COLUMNS, RunSummary, Sample } from "@/lib/types";

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// Build the CSV string from the API response and trigger a client-side download
// via a Blob — no server-side file generation.
function downloadCsv(runId: number, rows: Sample[]) {
  const header = CSV_COLUMNS.join(",");
  const body = rows
    .map((r) => CSV_COLUMNS.map((c) => csvCell(r[c])).join(","))
    .join("\n");
  const csv = `${header}\n${body}\n`;

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `dyno_run_${runId}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function fmtTs(ts: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

function fmtDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e < s) return "—";
  const secs = Math.round((e - s) / 1000);
  const m = Math.floor(secs / 60);
  const sec = secs % 60;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

export default function RunHistory() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [points, setPoints] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/runs", { cache: "no-store" })
      .then((r) => r.json())
      .then(setRuns)
      .catch(() => {});
  }, []);

  async function loadRun(id: number) {
    setSelected(id);
    setLoading(true);
    try {
      const rows: Sample[] = await fetch(`/api/run/${id}`, {
        cache: "no-store",
      }).then((r) => r.json());
      const t0 = rows.length ? new Date(rows[0].ts).getTime() : 0;
      setPoints(
        rows.map((s) => ({
          x: +((new Date(s.ts).getTime() - t0) / 1000).toFixed(1),
          rpm: s.rpm,
          torque: s.torque_ftlbs,
          hp: s.hp,
        }))
      );
    } finally {
      setLoading(false);
    }
  }

  async function exportRun(id: number) {
    const rows: Sample[] = await fetch(`/api/run/${id}`, {
      cache: "no-store",
    }).then((r) => r.json());
    downloadCsv(id, rows);
  }

  return (
    <div className="space-y-4">
      {selected !== null ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <h3 className="mb-2 text-sm font-medium text-zinc-300">
            Run #{selected} power curve {loading ? "— loading…" : ""}
          </h3>
          {points.length > 0 ? (
            <LiveChart points={points} xLabel="seconds since run start" />
          ) : (
            <p className="py-12 text-center text-zinc-500">
              {loading ? "Loading samples…" : "No samples for this run."}
            </p>
          )}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="px-4 py-2 font-medium">Run</th>
              <th className="px-4 py-2 font-medium">Started</th>
              <th className="px-4 py-2 font-medium">Ended</th>
              <th className="px-4 py-2 font-medium">Duration</th>
              <th className="px-4 py-2 font-medium">Notes</th>
              <th className="px-4 py-2 text-right font-medium">Samples</th>
              <th className="px-4 py-2 text-right font-medium">Export</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-zinc-500">
                  No runs yet.
                </td>
              </tr>
            ) : (
              runs.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => loadRun(r.id)}
                  className={`cursor-pointer border-t border-zinc-800 hover:bg-zinc-800/60 ${
                    selected === r.id ? "bg-zinc-800/80" : ""
                  }`}
                >
                  <td className="px-4 py-2 font-mono text-zinc-300">#{r.id}</td>
                  <td className="px-4 py-2 text-zinc-300">
                    {fmtTs(r.started_at)}
                  </td>
                  <td className="px-4 py-2 text-zinc-300">
                    {fmtTs(r.ended_at)}
                  </td>
                  <td className="px-4 py-2 text-zinc-300">
                    {fmtDuration(r.started_at, r.ended_at)}
                  </td>
                  <td className="px-4 py-2 text-zinc-400">{r.notes ?? "—"}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-zinc-300">
                    {r.sample_count.toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        exportRun(r.id);
                      }}
                      className="rounded bg-zinc-700 px-3 py-1 text-xs font-medium text-zinc-100 hover:bg-zinc-600"
                    >
                      CSV
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
