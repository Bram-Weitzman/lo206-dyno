"use client";

import { useEffect, useRef, useState } from "react";
import LiveChart, { ChartPoint } from "@/components/LiveChart";
import RunHistory from "@/components/RunHistory";
import StatusBar from "@/components/StatusBar";
import { Sample } from "@/lib/types";

const POLL_MS = 500; // 500ms fetch poll (see README: why polling, not WebSocket)
const WINDOW_S = 60; // rolling live-chart window

const MODE_LABELS = ["Manual", "PID", "Sweep"];

interface Buffered {
  tMs: number;
  rpm: number;
  torque: number;
  hp: number;
  setpoint: number;
}

export default function Page() {
  const [sample, setSample] = useState<Sample | null>(null);
  const [points, setPoints] = useState<ChartPoint[]>([]);
  const bufRef = useRef<Buffered[]>([]);
  const runRef = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;

    const tick = async () => {
      try {
        const res = await fetch("/api/live", { cache: "no-store" });
        const s: Sample | null = await res.json();
        if (!alive) return;

        if (!s) {
          setSample(null);
          return;
        }

        // A new run started: clear and restart the rolling window.
        if (runRef.current !== null && runRef.current !== s.run_id) {
          bufRef.current = [];
        }
        runRef.current = s.run_id;

        const now = Date.now();
        bufRef.current.push({
          tMs: now,
          rpm: s.rpm,
          torque: s.torque_ftlbs,
          hp: s.hp,
          setpoint: s.rpm_setpoint ?? 0,
        });
        const cutoff = now - WINDOW_S * 1000;
        bufRef.current = bufRef.current.filter((p) => p.tMs >= cutoff);

        setSample(s);
        setPoints(
          bufRef.current.map((p) => ({
            x: +((now - p.tMs) / 1000).toFixed(1), // seconds ago
            rpm: p.rpm,
            torque: p.torque,
            hp: p.hp,
            setpoint: p.setpoint,
          }))
        );
      } catch {
        // Keep last-good values; the logger/DB may be momentarily busy.
      }
    };

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <main className="mx-auto max-w-6xl space-y-8 p-4 md:p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-zinc-50">
          LO206 Dyno Dashboard
        </h1>
        <div className="flex items-center gap-3">
          {/* Pulsing dot: green=running, red=fault, grey=no data */}
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              sample?.sim_status === 1
                ? "bg-green-400 animate-pulse"
                : sample?.sim_status === 2
                ? "bg-red-400 animate-pulse"
                : "bg-zinc-600"
            }`}
          />
          <span className="text-sm text-zinc-400">
            {sample?.sim_status === 1
              ? `Live · Run #${sample.run_id} · ${
                  MODE_LABELS[sample.control_mode] ?? "?"
                }`
              : sample?.sim_status === 2
              ? "FAULT"
              : "No live run"}
          </span>
        </div>
      </header>

      <section className="space-y-4">
        <h2 className="text-sm font-medium uppercase tracking-widest text-zinc-500">
          Live telemetry
        </h2>
        <StatusBar sample={sample} />
        {sample?.limiter_active === 1 && (
          <div className="flex items-center justify-center gap-2 rounded-lg
            border border-red-800 bg-red-950/60 py-2 text-sm font-semibold
            uppercase tracking-widest text-red-400 animate-pulse">
            ⚠ Rev limiter active — samples excluded from power curve
          </div>
        )}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <LiveChart
            points={points}
            xLabel="seconds ago"
            reversed
            xDomain={[0, WINDOW_S]}
          />
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-medium uppercase tracking-widest text-zinc-500">
          Run history
        </h2>
        <RunHistory />
      </section>
    </main>
  );
}
