"use client";

import { useEffect, useRef, useState } from "react";
import LiveChart, { ChartPoint } from "@/components/LiveChart";
import RunHistory from "@/components/RunHistory";
import StatusBar from "@/components/StatusBar";
import { Sample } from "@/lib/types";

const POLL_MS = 500; // 500ms fetch poll (see README: why polling, not WebSocket)
const WINDOW_S = 60; // rolling live-chart window

interface Buffered {
  tMs: number;
  rpm: number;
  torque: number;
  hp: number;
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
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold text-zinc-50">
          LO206 Dyno Dashboard
        </h1>
        <span className="text-sm text-zinc-500">
          {sample ? `Run #${sample.run_id}` : "no live run"}
        </span>
      </header>

      <section className="space-y-4">
        <h2 className="text-sm font-medium uppercase tracking-widest text-zinc-500">
          Live
        </h2>
        <StatusBar sample={sample} />
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
