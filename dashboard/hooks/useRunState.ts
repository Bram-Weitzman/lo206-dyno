"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Sample } from "@/lib/types";

// Single derived run-state for the dashboard.
//
// Why this exists: before this hook, "is a run active / what mode / what phase"
// was derived independently in 3+ places (the top-right indicator off
// /api/live; the operator bar off local `openRun` + `readback`; the manual
// lock off the same). Those derivations froze stale readback after a run
// closed, surfaced PLC SWEEP_STATE from a prior run during the next PID run,
// and produced contradictions like "No run open" + "sweep running" in the
// same view. This hook owns all three polls and exposes ONE normalized
// `phase` enum + `lockReason`. Every consumer renders from the hook.
//
// Derivation table (read this when changing any consumer):
//
//   openRun  | mode    | safety | sweep_state | phase
//   ---------+---------+--------+-------------+-----------------------
//   null     | -       | -      | -           | idle
//   set      | (none)  | -      | -           | pid-armed *fallback
//   set      | PID     | 1      | -           | pid-armed
//   set      | PID     | 0      | -           | pid-stopped-open
//   set      | Manual  | 1      | -           | manual-armed
//   set      | Manual  | 0      | -           | manual-stopped-open
//   set      | Sweep   | 1      | 1           | sweep-armed
//   set      | Sweep   | 1      | 2           | sweep-complete-open
//   set      | Sweep   | 0      | *           | sweep-complete-open
//
// *fallback: an open run with no readback yet (the first ~1 poll interval
// after Start) is treated as armed so the manual panel stays safely locked
// until the first /api/command response lands.
//
// lockReason: non-null ONLY in *-armed phases where an automated loop is
// actively driving the engine. After Stop (safety_enable=0) it is null,
// matching the panel-lock fix from session 26ad22e — but now derived from
// the normalized phase rather than from raw readback fields, so a freeze
// or transient backend error cannot leave the lock stuck.

export interface RunRow {
  id: number;
  started_at: string;
  ended_at: string | null;
  notes: string | null;
  sample_count: number;
}

export interface CommandReadback {
  target_rpm: number;
  control_mode: number;
  safety_enable: number;
  sweep_start: number;
  sweep_end: number;
  sweep_step: number;
  sweep_dwell: number;
  sweep_state: number;
  throttle: number;
}

export type RunPhase =
  | "idle"
  | "pid-armed"
  | "pid-stopped-open"
  | "manual-armed"
  | "manual-stopped-open"
  | "sweep-armed"
  | "sweep-complete-open";

export interface RunState {
  phase: RunPhase;
  openRun: RunRow | null;
  readback: CommandReadback | null;
  live: Sample | null;
  lockReason: string | null;
  sweepActive: boolean;
  postCommand: (body: Record<string, unknown>) => Promise<CommandReadback>;
  openNewRun: (notes: string) => Promise<RunRow>;
  endRun: () => Promise<RunRow | null>;
  setSweepActive: (v: boolean) => void;
  refreshOpenRun: () => Promise<RunRow | null>;
}

const RUN_POLL_MS = 1500;
const COMMAND_POLL_MS = 1000;
const LIVE_POLL_MS = 500;

const MODE_MANUAL = 0;
const MODE_PID = 1;
const MODE_SWEEP = 2;
const SWEEP_STATE_COMPLETE = 2;

function derivePhase(
  openRun: RunRow | null,
  rb: CommandReadback | null,
): RunPhase {
  if (!openRun) return "idle";
  if (!rb) return "pid-armed";
  const mode = rb.control_mode;
  const armed = rb.safety_enable === 1;
  if (mode === MODE_PID) return armed ? "pid-armed" : "pid-stopped-open";
  if (mode === MODE_MANUAL) return armed ? "manual-armed" : "manual-stopped-open";
  if (mode === MODE_SWEEP) {
    if (!armed) return "sweep-complete-open";
    if (rb.sweep_state === SWEEP_STATE_COMPLETE) return "sweep-complete-open";
    return "sweep-armed";
  }
  return "pid-armed";
}

function deriveLockReason(phase: RunPhase): string | null {
  if (phase === "pid-armed") return "PID loop is holding — stop it first";
  if (phase === "sweep-armed") return "sweep is running — stop it first";
  return null;
}

export function useRunState(): RunState {
  const [openRun, setOpenRun] = useState<RunRow | null>(null);
  const [readback, setReadback] = useState<CommandReadback | null>(null);
  const [live, setLive] = useState<Sample | null>(null);
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
      return null;
    }
  }, []);

  // /api/runs poll: drives openRun.
  useEffect(() => {
    alive.current = true;
    refreshOpenRun();
    const id = setInterval(refreshOpenRun, RUN_POLL_MS);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [refreshOpenRun]);

  // /api/command poll: drives readback. Runs ONLY while a run is open. On
  // close, clears readback so no consumer ever reads stale values — this is
  // the fix for the "No run open + sweep running" class of bug.
  useEffect(() => {
    if (!openRun) {
      setReadback(null);
      return;
    }
    let aliveLoop = true;
    const poll = async () => {
      try {
        const res = await fetch("/api/command", { cache: "no-store" });
        const data = await res.json();
        if (!aliveLoop || !data.ok) return;
        const rb = data.readback as CommandReadback;
        setReadback(rb);
        // Sweep auto-close: only when WE started this session's sweep.
        // sweepActive guards against a stale SWEEP_STATE=2 from a prior
        // sweep tearing down an unrelated run.
        if (sweepActive && rb.sweep_state === SWEEP_STATE_COMPLETE) {
          const open = await refreshOpenRun();
          if (open) {
            await fetch(`/api/run/${open.id}`, { method: "PATCH" });
            await refreshOpenRun();
          }
          setSweepActive(false);
        }
      } catch {
        // transient — keep polling
      }
    };
    poll();
    const id = setInterval(poll, COMMAND_POLL_MS);
    return () => {
      aliveLoop = false;
      clearInterval(id);
    };
  }, [openRun, sweepActive, refreshOpenRun]);

  // /api/live poll: drives live (engine telemetry sample).
  useEffect(() => {
    let aliveLoop = true;
    const tick = async () => {
      try {
        const res = await fetch("/api/live", { cache: "no-store" });
        const s: Sample | null = await res.json();
        if (!aliveLoop) return;
        setLive(s);
      } catch {
        // keep last-known value
      }
    };
    tick();
    const id = setInterval(tick, LIVE_POLL_MS);
    return () => {
      aliveLoop = false;
      clearInterval(id);
    };
  }, []);

  const postCommand = useCallback(
    async (bodyObj: Record<string, unknown>): Promise<CommandReadback> => {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bodyObj),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        const errStr =
          typeof data?.error === "string" && data.error.length > 0
            ? data.error
            : `command "${String(bodyObj.action ?? "")}" failed`;
        throw new Error(errStr);
      }
      const rb = data.readback as CommandReadback;
      if (alive.current) setReadback(rb);
      return rb;
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

  const endRun = useCallback(async (): Promise<RunRow | null> => {
    const open = openRun;
    if (!open) return null;
    const res = await fetch(`/api/run/${open.id}`, { method: "PATCH" });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error ?? "end run failed");
    setSweepActive(false);
    await refreshOpenRun();
    return { ...open, ended_at: data.ended_at } as RunRow;
  }, [openRun, refreshOpenRun]);

  // Enforce the core invariant structurally: when no run is open, readback is
  // ABSENT to every consumer — regardless of a late postCommand response that
  // set it after the run closed. This race happens when a sweep auto-completes
  // (run closes → openRun null → the poll effect clears readback) at the same
  // instant the operator hits E-Stop/Stop: that command's postCommand resolves
  // afterward and calls setReadback(rb), re-populating readback with no open
  // run. The poll effect only clears readback on an openRun *change*, so it
  // never fires again. Gating here makes "openRun null ⇒ readback null" hold no
  // matter how the raw state got set, killing the "No run open + sweep complete"
  // contradiction at the source.
  const visibleReadback = openRun ? readback : null;
  const phase = derivePhase(openRun, visibleReadback);
  const lockReason = deriveLockReason(phase);

  return {
    phase,
    openRun,
    readback: visibleReadback,
    live,
    lockReason,
    sweepActive,
    postCommand,
    openNewRun,
    endRun,
    setSweepActive,
    refreshOpenRun,
  };
}
