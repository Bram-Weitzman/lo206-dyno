"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Operator command panel — the dashboard's first WRITE surface.
//
//   Start    -> POST /api/runs (open a run row) THEN POST /api/command start
//               (CONTROL_MODE=PID, SAFETY_ENABLE=1). Run is opened FIRST so the
//               logger attaches and captures from spin-up.
//   End Run  -> PATCH /api/run/[id] (stamp ended_at). Does NOT stop the engine.
//   Stop     -> POST /api/command stop  (SAFETY_ENABLE=0). Does NOT close the run.
//   E-stop   -> POST /api/command estop (SAFETY_ENABLE=0), immediate, no confirm.
//
// Ending a run and stopping the engine are deliberately independent actions.
// All Modbus writes go through /api/command (OpenPLC :502); this component never
// talks Modbus directly.

interface RunRow {
  id: number;
  started_at: string;
  ended_at: string | null;
  notes: string | null;
  sample_count: number;
}

interface CommandReadback {
  target_rpm: number;
  control_mode: number;
  safety_enable: number;
}

const RUN_POLL_MS = 1500;
const MODE_LABELS = ["Manual", "PID", "Sweep"];

export default function OperatorControls() {
  const [openRun, setOpenRun] = useState<RunRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [readback, setReadback] = useState<CommandReadback | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  // The open run is the newest /api/runs row with ended_at === null (the list is
  // returned newest-first). Drives the Start/End-Run enabled states.
  const refreshOpenRun = useCallback(async () => {
    try {
      const res = await fetch("/api/runs", { cache: "no-store" });
      const rows: RunRow[] = await res.json();
      const open = rows.find((r) => r.ended_at === null) ?? null;
      if (alive.current) setOpenRun(open);
    } catch {
      /* keep last-known state; the DB may be momentarily busy */
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    refreshOpenRun();
    const id = setInterval(refreshOpenRun, RUN_POLL_MS);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [refreshOpenRun]);

  const sendCommand = useCallback(
    async (action: "start" | "stop" | "estop"): Promise<CommandReadback> => {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error ?? `command "${action}" failed`);
      }
      setReadback(data.readback as CommandReadback);
      return data.readback as CommandReadback;
    },
    [],
  );

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // 1) Open the run first so the logger attaches before the engine spins up.
      const res = await fetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: "dashboard operator start" }),
      });
      const run: RunRow = await res.json();
      // 2) Enable the engine (CONTROL_MODE=PID, SAFETY_ENABLE=1).
      const rb = await sendCommand("start");
      setStatus(
        `Run #${run.id} opened · engine enabled (mode ${
          MODE_LABELS[rb.control_mode] ?? rb.control_mode
        }, target ${rb.target_rpm} RPM)`,
      );
      await refreshOpenRun();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sendCommand, refreshOpenRun]);

  const onEndRun = useCallback(async () => {
    if (!openRun) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/run/${openRun.id}`, { method: "PATCH" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "end run failed");
      setStatus(`Run #${openRun.id} ended at ${data.ended_at}`);
      await refreshOpenRun();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [openRun, refreshOpenRun]);

  const onStop = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const rb = await sendCommand("stop");
      setStatus(`Stop sent · SAFETY_ENABLE=${rb.safety_enable}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sendCommand]);

  // No confirm dialog — the brief requires the e-stop to be immediate. Not gated
  // on `busy` so it always fires. On the real rig this sits beside a physically
  // wired E-stop; this software button is a convenience, NOT the safety device.
  const onEstop = useCallback(async () => {
    setError(null);
    try {
      const rb = await sendCommand("estop");
      setStatus(`E-STOP sent · SAFETY_ENABLE=${rb.safety_enable}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [sendCommand]);

  const runOpen = openRun !== null;

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4 md:flex-row md:items-stretch md:justify-between">
      {/* Run + engine controls */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onStart}
          disabled={runOpen || busy}
          className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
        >
          ▶ Start
        </button>
        <button
          type="button"
          onClick={onEndRun}
          disabled={!runOpen || busy}
          className="rounded-md bg-zinc-700 px-5 py-2.5 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-600 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
        >
          ■ End Run
        </button>
        <button
          type="button"
          onClick={onStop}
          disabled={busy}
          className="rounded-md bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
        >
          ⏹ Stop
        </button>
      </div>

      {/* Emergency stop — large, always visible, visually distinct. */}
      <button
        type="button"
        onClick={onEstop}
        className="flex items-center justify-center rounded-lg border-2 border-red-400 bg-red-600 px-8 py-3 text-base font-extrabold uppercase tracking-widest text-white shadow-lg shadow-red-900/40 transition hover:bg-red-500 active:scale-95"
      >
        ⨯ Emergency Stop
      </button>

      {/* Run state + last-command read-back */}
      <div className="flex min-w-[16rem] flex-col justify-center gap-1 text-sm md:text-right">
        <span className="text-zinc-400">
          {runOpen ? (
            <>
              Run <span className="font-mono text-zinc-200">#{openRun!.id}</span>{" "}
              open
            </>
          ) : (
            "No run open"
          )}
        </span>
        {readback && (
          <span className="font-mono text-xs text-zinc-500">
            readback · target {readback.target_rpm} · mode{" "}
            {MODE_LABELS[readback.control_mode] ?? readback.control_mode} · enable{" "}
            {readback.safety_enable}
          </span>
        )}
        {status && !error && (
          <span className="text-xs text-emerald-400">{status}</span>
        )}
        {error && <span className="text-xs text-red-400">⚠ {error}</span>}
      </div>
    </div>
  );
}
