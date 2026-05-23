"use client";

import { useCallback, useState } from "react";
import type { RunState } from "@/hooks/useRunState";

// Operator command panel — the dashboard's WRITE surface.
//
//   Start (PID) -> POST /api/runs (open a run) THEN /api/command start with the
//                  operator's TARGET_RPM (CONTROL_MODE=PID, SAFETY_ENABLE=1).
//   Start Sweep -> POST /api/runs THEN /api/command start_sweep (writes the four
//                  sweep params + CONTROL_MODE=SWEEP + SAFETY_ENABLE=1). The PLC
//                  steps the setpoint and drops SAFETY_ENABLE itself at the end;
//                  the hook polls SWEEP_STATE and auto-closes the run on 2.
//   End Run     -> PATCH /api/run/[id] (stamp ended_at). Does NOT stop the engine.
//   Stop        -> /api/command stop  (SAFETY_ENABLE=0). Does NOT close the run.
//   E-stop      -> /api/command estop (SAFETY_ENABLE=0), immediate, no confirm.
//
// All run-state (openRun, readback, phase, lockReason) and the RunRow /
// CommandReadback types come from the single useRunState() hook instance,
// passed in as `run`. All Modbus I/O routes through the hook too. This panel
// owns NO run-state polling and NO run-state types of its own — it only holds
// form-input + UI-feedback state (target/sweep params, busy/status/error).
// See hooks/useRunState.ts.

const MODE_LABELS = ["Manual", "PID", "Sweep"];
const SWEEP_STATE_LABELS = ["idle", "running", "complete"];

// Must match plc/register_map.md (the contract). The API route and the PLC clamp
// too; this is the first line.
const LIMITS = {
  pid: { lo: 3200, hi: 6100 }, // PID hold target band (re-probed floor ~3360; a target below it sits at the floor; redline 6100)
  start: { lo: 2500, hi: 6100 },
  end: { lo: 2500, hi: 6100 },
  step: { lo: 100, hi: 1000 },
  dwell: { lo: 500, hi: 30000 },
};

function clampInt(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo;
  return Math.min(hi, Math.max(lo, Math.round(v)));
}

export default function OperatorControls({ run }: { run: RunState }) {
  const { openRun, readback, phase, postCommand, openNewRun, endRun,
    refreshOpenRun, setSweepActive } = run;

  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // PID hold target.
  const [pidTarget, setPidTarget] = useState(4000);

  // Sweep params (defaults match register_map.md: floor-aware start 3400).
  const [sweepStart, setSweepStart] = useState(3400);
  const [sweepEnd, setSweepEnd] = useState(6100);
  const [sweepStep, setSweepStep] = useState(400);
  const [sweepDwell, setSweepDwell] = useState(2000);

  // Manual diagnostics: brake-valve override slider value (%).
  const [manualValve, setManualValve] = useState(0);

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const target = clampInt(pidTarget, LIMITS.pid.lo, LIMITS.pid.hi);
      const run0 = await openNewRun(`dashboard PID hold ${target} RPM`);
      // Send the operator's target so the loop holds the chosen RPM, not a stale
      // register value.
      const rb = await postCommand({ action: "start", target });
      setStatus(`Run #${run0.id} opened · PID holding ${rb.target_rpm} RPM`);
      await refreshOpenRun();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [pidTarget, openNewRun, postCommand, refreshOpenRun]);

  // Mid-run PID target update. Writes ONLY %QW101 — does not touch
  // CONTROL_MODE or SAFETY_ENABLE, so the existing PID loop just re-tracks the
  // new setpoint without re-arming. One deliberate write per click; the field
  // and slider stay editable during a PID run so the operator can dial in.
  const onUpdateTarget = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const target = clampInt(pidTarget, LIMITS.pid.lo, LIMITS.pid.hi);
      const rb = await postCommand({ action: "set_target", target });
      setStatus(`Target updated · PID holding ${rb.target_rpm} RPM`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [pidTarget, postCommand]);

  const onStartSweep = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const start = clampInt(sweepStart, LIMITS.start.lo, LIMITS.start.hi);
      const end = Math.max(start, clampInt(sweepEnd, LIMITS.end.lo, LIMITS.end.hi));
      const step = clampInt(sweepStep, LIMITS.step.lo, LIMITS.step.hi);
      const dwell = clampInt(sweepDwell, LIMITS.dwell.lo, LIMITS.dwell.hi);
      const run0 = await openNewRun(
        `dashboard sweep ${start}-${end} RPM, step ${step}, dwell ${dwell}ms`,
      );
      const rb = await postCommand({ action: "start_sweep", start, end, step, dwell });
      setSweepActive(true);
      setStatus(
        `Sweep started · run #${run0.id} · ${rb.sweep_start}→${rb.sweep_end} RPM, step ${rb.sweep_step}, dwell ${rb.sweep_dwell}ms`,
      );
      await refreshOpenRun();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sweepStart, sweepEnd, sweepStep, sweepDwell, openNewRun, postCommand, refreshOpenRun, setSweepActive]);

  const onEndRun = useCallback(async () => {
    const open = openRun;
    if (!open) return;
    setBusy(true);
    setError(null);
    try {
      const ended = await endRun();
      setStatus(`Run #${open.id} ended at ${ended?.ended_at ?? "?"}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [openRun, endRun]);

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
  }, [postCommand, setSweepActive]);

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
  }, [postCommand, setSweepActive]);

  // Manual throttle (accelerator / lift-off): toggle the THROTTLE coil. Writes
  // ONLY the coil. During a PID/sweep run the PLC forces WOT, so this is only
  // meaningful in manual/idle; the button is disabled while an automated run is
  // open (see disable gate below).
  const onToggleThrottle = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const next = readback?.throttle === 1 ? false : true;
      const rb = await postCommand({ action: "set_throttle", throttle: next });
      setStatus(`Throttle ${rb.throttle === 1 ? "WIDE-OPEN" : "idle"}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [readback, postCommand]);

  // Manual brake-valve override (diagnostics). Sends CONTROL_MODE=manual +
  // enable + valve%, so it is mutually exclusive with PID/sweep -- it cannot
  // fight the PID. Disabled while an automated run is open.
  const onSetValve = useCallback(
    async (pct: number) => {
      setBusy(true);
      setError(null);
      try {
        const rb = await postCommand({ action: "set_valve", valve: pct });
        setStatus(`Manual valve ${pct}% · mode ${MODE_LABELS[rb.control_mode]}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [postCommand],
  );

  const runOpen = openRun !== null;
  // Run-state booleans derive from the hook's normalized `phase`, never from
  // raw readback fields — so a poll freeze or transient backend error cannot
  // leave them stuck (the bug class this consolidation kills).
  const pidHolding = phase === "pid-armed";
  // "PID run open" gates the mid-run Update Target affordance: a PID run is
  // open whether the loop is currently armed or stopped (mode stays PID until
  // a different mode is commanded).
  const pidRunOpen = phase === "pid-armed" || phase === "pid-stopped-open";
  const inSweep = phase === "sweep-armed" || phase === "sweep-complete-open";

  // Manual throttle + valve lock. lockReason comes straight from the hook,
  // which derives it from the normalized run `phase` (non-null only in a
  // *-armed phase) — NOT from raw readback fields. A poll freeze or transient
  // backend error can therefore no longer leave the lock stuck on. This is the
  // architectural fix for bug D (stale manual-lock). The hint text reuses
  // lockReason verbatim. (set_valve also forces CONTROL_MODE=manual
  // server-side, a second guard.)
  const lockReason = run.lockReason;
  const manualLocked = lockReason !== null;

  return (
    <div className="flex flex-col gap-4">
      {/* Row 1: run/stop controls, e-stop, read-back */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4 md:flex-row md:items-stretch md:justify-between">
        <div className="flex flex-wrap items-center gap-3">
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
              readback · mode {MODE_LABELS[readback.control_mode] ?? readback.control_mode} · target{" "}
              {readback.target_rpm} · enable {readback.safety_enable} · sweep{" "}
              {SWEEP_STATE_LABELS[readback.sweep_state] ?? readback.sweep_state}
            </span>
          )}
          {status && !error && <span className="text-xs text-emerald-400">{status}</span>}
          {error && <span className="text-xs text-red-400">⚠ {error}</span>}
        </div>
      </div>

      {/* Row 2: PID hold run mode */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
            PID hold (constant RPM)
          </h3>
          {pidHolding && readback && (
            <span className="font-mono text-xs text-emerald-400">
              holding · target {readback.target_rpm} RPM
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs text-zinc-400">
            Target RPM
            <input
              type="number"
              min={LIMITS.pid.lo}
              max={LIMITS.pid.hi}
              step={100}
              value={pidTarget}
              onChange={(e) => setPidTarget(Number(e.target.value))}
              className="w-28 rounded-md border border-zinc-700 bg-zinc-800 px-2 py-1.5 font-mono text-sm text-zinc-100"
            />
          </label>
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-xs text-zinc-400">
            Hold RPM: <span className="font-mono text-zinc-200">{pidTarget} RPM</span>
            <input
              type="range"
              min={LIMITS.pid.lo}
              max={LIMITS.pid.hi}
              step={100}
              value={pidTarget}
              onChange={(e) => setPidTarget(Number(e.target.value))}
              className="accent-emerald-500"
            />
          </label>
          {pidRunOpen ? (
            <button
              type="button"
              onClick={onUpdateTarget}
              disabled={busy}
              className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
            >
              ↻ Update Target
            </button>
          ) : (
            <button
              type="button"
              onClick={onStart}
              disabled={runOpen || busy}
              className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500"
            >
              ▶ Start (PID)
            </button>
          )}
        </div>
        <p className="text-xs text-zinc-600">
          Opens a run and holds a constant RPM via the PID. Usable band 3200-6100
          RPM (brake-capacity floor ~3360 RPM). While a PID run is open, change
          the target and click Update Target to retune the hold without ending
          the run.
        </p>
      </div>

      {/* Row 3: sweep run mode */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
            Stepped sweep (auto torque curve)
          </h3>
          {inSweep && readback && (
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
          itself and auto-closes the run. Brake-capacity floor ~3360 RPM (clutch
          removed); starting below it just saturates the low steps.
        </p>
      </div>

      {/* Row 4: manual / diagnostics — binary throttle + manual valve override */}
      <div className="flex flex-col gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
            Manual / diagnostics
          </h3>
          {readback && (
            <span
              className={`font-mono text-xs ${readback.throttle === 1 ? "text-orange-400" : "text-zinc-500"}`}
            >
              throttle {readback.throttle === 1 ? "WIDE-OPEN" : "idle"}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-end gap-4">
          {/* Binary throttle: tap to WOT, tap again to idle. */}
          <button
            type="button"
            onClick={onToggleThrottle}
            disabled={manualLocked || busy}
            className={`rounded-md px-5 py-2.5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-500 ${
              readback?.throttle === 1
                ? "bg-orange-600 hover:bg-orange-500"
                : "bg-zinc-700 hover:bg-zinc-600"
            }`}
          >
            {readback?.throttle === 1 ? "↓ Lift off (idle)" : "↑ Accelerator (WOT)"}
          </button>

          {/* Manual brake-valve override slider + deliberate Apply button. */}
          <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-xs text-zinc-400">
            Manual valve: <span className="font-mono text-zinc-200">{manualValve}%</span>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={manualValve}
              disabled={manualLocked}
              onChange={(e) => setManualValve(Number(e.target.value))}
              className="accent-orange-500 disabled:opacity-40"
            />
          </label>
          <button
            type="button"
            onClick={() => onSetValve(manualValve)}
            disabled={manualLocked || busy}
            className="rounded-md bg-zinc-700 px-5 py-2.5 text-sm font-semibold text-zinc-100 transition hover:bg-zinc-600 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600"
          >
            Apply valve
          </button>
        </div>
        <p className="text-xs text-zinc-600">
          Diagnostics only. The throttle button toggles the engine accelerator
          (wide-open vs idle); at idle the engine makes no power and coasts down.
          The manual valve applies brake directly — it sends CONTROL_MODE=manual,
          which is mutually exclusive with PID/sweep, so it cannot fight the PID.
          {lockReason ? ` Disabled now: ${lockReason}.` : ""}
        </p>
      </div>
    </div>
  );
}
