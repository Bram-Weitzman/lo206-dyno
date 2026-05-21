"use client";

import { Sample } from "@/lib/types";

const MODE_LABELS = ["Manual", "PID", "Sweep"];
const STATUS_LABELS = ["Stopped", "Running", "Fault"];

// CHT and pressure accent colors — kept as constants so they can
// be referenced for the bottom border too.
const CHT_COLOR = "#fb923c";      // orange-400
const PRESSURE_COLOR = "#a78bfa"; // violet-400

function fmt(n: number | undefined | null, digits = 0): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "--";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function MetricCard({
  label,
  value,
  unit,
  color,
  borderColor,
  flash,
}: {
  label: string;
  value: string;
  unit?: string;
  color: string;
  borderColor?: string;
  flash?: boolean; // true = pulse red (limiter / fault highlight)
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-1 rounded-lg
        border border-zinc-800 bg-zinc-900 px-4 py-4
        ${flash ? "animate-pulse" : ""}`}
      style={{ borderBottomColor: borderColor ?? color, borderBottomWidth: 3 }}
    >
      <span className="font-mono text-4xl font-bold tabular-nums leading-none"
        style={{ color }}>
        {value}
        {unit ? (
          <span className="ml-1 text-lg font-normal text-zinc-400">{unit}</span>
        ) : null}
      </span>
      <span className="text-xs font-medium uppercase tracking-widest text-zinc-500">
        {label}
      </span>
    </div>
  );
}

export default function StatusBar({ sample }: { sample: Sample | null }) {
  const s = sample;

  const statusLabel = s
    ? (STATUS_LABELS[s.sim_status] ?? String(s.sim_status))
    : "--";
  const modeLabel = s
    ? (MODE_LABELS[s.control_mode] ?? String(s.control_mode))
    : "--";

  const statusColor = !s
    ? "#a1a1aa"
    : s.sim_status === 2
    ? "#f87171"
    : s.sim_status === 1
    ? "#4ade80"
    : "#a1a1aa";

  return (
    <div className="grid grid-cols-4 gap-3">
      {/* Row 1: power metrics */}
      <MetricCard
        label="RPM"
        value={fmt(s?.rpm)}
        color="#fbbf24"
      />
      <MetricCard
        label="Torque"
        value={fmt(s?.torque_ftlbs, 1)}
        unit="ft-lbs"
        color="#22d3ee"
      />
      <MetricCard
        label="HP"
        value={fmt(s?.hp, 1)}
        color="#f472b6"
      />
      <MetricCard
        label="Valve"
        value={fmt(s?.valve_pct, 1)}
        unit="%"
        color="#f4f4f5"
      />

      {/* Row 2: engine state */}
      <MetricCard
        label="CHT"
        value={fmt(s?.cht_c)}
        unit="°C"
        color={CHT_COLOR}
      />
      <MetricCard
        label="Pressure"
        value={fmt(s?.pressure)}
        unit="PSI"
        color={PRESSURE_COLOR}
      />
      <MetricCard
        label="Mode"
        value={modeLabel}
        color="#a1a1aa"
      />
      <MetricCard
        label="Status"
        value={statusLabel}
        color={statusColor}
        flash={s?.sim_status === 2}
      />
    </div>
  );
}
