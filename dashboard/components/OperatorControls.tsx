"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Operator command panel — the dashboard's WRITE surface.
//
//   Start       -> POST /api/runs (open a run) THEN /api/command start
//                  (CONTROL_MODE=PID, SAFETY_ENABLE=1).
//   Start Sweep -> POST /api/runs THEN /api/command start_sweep (writes the four
//                  sweep params + CONTROL_MODE=SWEEP + SAFETY_ENABLE=1). The PLC
//                  steps the setpoint and drops SAFETY_ENABLE itself at the end;
//                  this panel polls SWEEP_STATE and auto-closes the run on 2.
//   End Run     -> PATCH /api/run/[id] (stamp ended_at). Does NOT stop the engine.
//   Stop        -> /api/command stop  (SAFETY_ENABLE=0). Does NOT close the run.
//   E-stop      -> /api/command estop (SAFETY_ENABLE=0), immediate, no confirm.
//
// All Modbus I/O goes through /api/command (OpenPLC :502); this component never
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
  sweep_start: number;
  sweep_end: number;
  sweep_step: number;
  sweep_dwell: number;
  sweep_state: number; // 0 idle / 1 running / 2 complete
}

const RUN_POLL_MS = 1500;
const SWEEP_POLL_MS = 1000;
const MODE_LABELS = ["Manual", "PID", "Sweep"];
const SWEEP_STATE_LABELS = ["idle", "running", "complete"];

// Must match plc/register_map.md (the contract). The API route and the PLC clamp
// too; this is the first line.
const LIMITS = {
  start: { lo: 2500, hi: 6100 },
  end: { lo: 2500, hi: 6100 },
  step: { lo: 100, hi: 1000 },
  dwell: { lo: 500, hi: 30000 },
};

function clampInt(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo;
  return Math.min(hi, Math.max(lo, Math.round(v)));
}

export default function OperatorControls() {
  const [openRun, setOpenRun] = useState<RunRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [readback, setReadback] = useState<CommandReadback | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Sweep params (defaults match register_map.md: floor-aware start 3200).
  const [sweepStart, setSweepStart] = useState(3200);
  const [sweepEnd, setSweepEnd] = useState(6100);
  const [sweepStep, setSweepStep] = useState(400);
  const [sweepDwell, setSweepDwell] = useState(2000);
  // True only while WE are running a sweep — guards auto-close so a stale
  // SWEEP_STATE=2 from a previous sweep cannot close an unrelated run.
  const [sweepActive, setSweepActive] = useState(false);

  const alive = useRef(true);

  const refreshOpenRun = useCallback(async (): Promise<RunRow | null> => {
    try {
      const res = await fetch("/api/runs", { cache: "no-store" });
      const rows: RunRow[] = await res.json();
      const open = rows.find((r) => r.ended_at === null) ?? null;
      if (alive.current) setOpenRun(open);
      return open;
    } catch {
      return null; // keep last-known state; the DB may be momentarily busy
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

  // While a sweep is active, poll SWEEP_STATE; auto-close the run when it hits 2.
  useEffect(() => {
    if (!sweepActive) return;
    let live = true;
    const poll = async () => {
      try {
        const res = await fetch("/api/command", { cache: "no-store" });
        const data = await res.json();
        if (!live || !data.ok) return;
        const rb = data.readback as CommandReadback;
        setReadback(rb);
        if (rb.sweep_state === 2) {
          // Sweep finished: the PLC already dropped SAFETY_ENABLE. Close the run
          // so a sweep is one self-contained action.
          const open = await refreshOpenRun();
          if (open) {
            await fetch(`/api/run/${open.id}`, { method: "PATCH" });
            await refreshOpenRun();
            setStatus(`Sweep complete · run #${open.id} auto-closed`);
          } else {
            setStatus("Sweep complete");
          }
          setSweepActive(false);
        }
      } catch {
        /* transient; keep polling */
      }
    };
    poll();
    const id = setInterval(poll, SWEEP_POLL_MS);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, [sweepActive, refreshOpenRun]);

  const postCommand = useCallback(
    async (bodyObj: Record<string, unknown>): Promise<CommandReadback> => {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyObj),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error ?? `command "${bodyObj.action}" failed`);
      }
      setReadback(data.readback as CommandReadback);
      return data.readback as CommandReadback;
    },
    [],
  );

  const openNewRun = useCallback(async (notes: string): Promise<RunRow> => {
    const res = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes }),
    });
    return (await res.json()) as RunRow;
  }, []);

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const run = await openNewRun("dashboard operator start (PID hold)");
      const rb = await postCommand({ action: "start" });
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
  }, [openNewRun, postCommand, refreshOpenRun]);

  const onStartSweep = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const start = clampInt(sweepStart, LIMITS.start.lo, LIMITS.start.hi);
      const end = Math.max(start, clampInt(sweepEnd, LIMITS.end.lo, LIMITS.end.hi));
      const step = clampInt(sweepStep, LIMITS.step.lo, LIMITS.step.hi);
      const dwell = clampInt(sweepDwell, LIMITS.dwell.lo, LIMITS.dwell.hi);
      const run = await openNewRun(
        `dashboard sweep ${start}-${end} RPM, step ${step}, dwell ${dwell}ms`,
      );
      const rb = await postCommand({ action: "start_sweep", start, end, step, dwell });
      setSweepActive(true);
      setStatus(
        `Sweep started · run #${run.id} · ${rb.sweep_start}→${rb.sweep_end} RPM, step ${rb.sweep_step}, dwell ${rb.sweep_dwell}ms`,
      );
      await refreshOpenRun();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sweepStart, sweepEnd, sweepStep, sweepDwell, openNewRun, postCommand, refreshOpenRun]);

  const onEndRun = useCallback(async () => {
    if (!openRun) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/run/${openRun.id}`, { method: "PATCH" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "end run failed");
      setSweepActive(false);
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
      const rb = await postCommand({ action: "stop" });
      setSweepActive(false); // a manual stop ends any sweep; run stays open
      setStatus(`Stop sent · SAFETY_ENABLE=${rb.safety_enable}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [postCommand]);

  // No confirm dialog — immediate. Not gated on `busy` so it always fires. On the
  // real rig this sits beside a physically wired E-stop; this software button is
  // a convenience, NOT the safety device.
  const onEstop = useCallback(async () => {
    setError(null);
    setSweepActive(false);
    try {
      const rb = await postCommand({ action: "estop" });
      setStatus(`E-STOP sent · SAFETY_ENABLE=${rb.safety_enable}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [postCommand]);

  const runOpen = openRun !== null;

  return (
    <div className="flex flex-col gap-4">
      {/* Row 1: run + engine controls, e-stop, read-back */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4 md:flex-row md:items-stretch md:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onStart}
            disabled={runOpen || busy}
            className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
          >
            ▶ Start (PID)
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

        <button
          type="button"
          onClick={onEstop}
          className="flex items-center justify-center rounded-lg border-2 border-red-400 bg-red-600 px-8 py-3 text-base font-extrabold uppercase tracking-widest text-white shadow-lg shadow-red-900/40 transition hover:bg-red-500 active:scale-95"
        >
          ⨯ Emergency Stop
        </button>

        <div className="flex min-w-[16rem] flex-col justify-center gap-1 text-sm md:text-right">
          <span className="text-zinc-400">
            {runOpen ? (
              <>
                Run <span className="font-mono text-zinc-200">#{openRun!.id}</span> open
              </>
            ) : (
              "No run open"
            )}
          </span>
          {readback && (
            <span className="font-mono text-xs text-zinc-500">
              readback · mode {MODE_LABELS[readback.control_mode] ?? readback.control_mode} · enable{" "}
              {readback.safety_enable} · sweep {SWEEP_STATE_LABELS[readback.sweep_state] ?? readback.sweep_state}
            </span>
          )}
          {status && !error && <span className="text-xs text-emerald-400">{status}</span>}
          {error && <span className="text-xs text-red-400">⚠ {error}</span>}
        </div>
      </div>

      {/* Row 2: sweep run mode */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
            Stepped sweep (auto torque curve)
          </h3>
          {sweepActive && readback && (
            <span className="font-mono text-xs text-sky-400">
              sweep {SWEEP_STATE_LABELS[readback.sweep_state] ?? readback.sweep_state}
              {readback.sweep_state === 1 ? ` · target ${readback.target_rpm} RPM` : ""}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            Start RPM
            <input
              type="number"
              min={LIMITS.start.lo}
              max={LIMITS.start.hi}
              step={100}
              value={sweepStart}
              onChange={(e) => setSweepStart(Number(e.target.value))}
              className="w-28 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 font-mono text-sm text-zinc-100"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            End RPM
            <input
              type="number"
              min={LIMITS.end.lo}
              max={LIMITS.end.hi}
              step={100}
              value={sweepEnd}
              onChange={(e) => setSweepEnd(Number(e.target.value))}
              className="w-28 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 font-mono text-sm text-zinc-100"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            Step RPM
            <input
              type="number"
              min={LIMITS.step.lo}
              max={LIMITS.step.hi}
              step={50}
              value={sweepStep}
              onChange={(e) => setSweepStep(Number(e.target.value))}
              className="w-28 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 font-mono text-sm text-zinc-100"
            />
          </label>
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-xs text-zinc-400">
            Dwell per step: <span className="font-mono text-zinc-200">{sweepDwell} ms</span>
            <input
              type="range"
              min={LIMITS.dwell.lo}
              max={LIMITS.dwell.hi}
              step={500}
              value={sweepDwell}
              onChange={(e) => setSweepDwell(Number(e.target.value))}
              className="accent-sky-500"
            />
          </label>
          <button
            type="button"
            onClick={onStartSweep}
            disabled={runOpen || busy}
            className="rounded-md bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
          >
            ⟳ Start Sweep
          </button>
        </div>
        <p className="text-xs text-zinc-600">
          Walks RPM up the band, dwelling at each step so torque settles, then ends
          itself and auto-closes the run. Brake-capacity floor ~3135 RPM (clutch
          removed); starting below it just saturates the low steps.
        </p>
      </div>
    </div>
  );
}
