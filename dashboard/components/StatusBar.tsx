"use client";

import { Sample } from "@/lib/types";

const MODE_LABELS = ["Manual", "PID", "Sweep"];
const STATUS_LABELS = ["Stopped", "Running", "Fault"];

function fmt(n: number | undefined, digits = 0): string {
  if (n === undefined || n === null || Number.isNaN(n)) return "--";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function Field({
  label,
  value,
  unit,
  accent,
}: {
  label: string;
  value: string;
  unit?: string;
  accent?: string;
}) {
  return (
    <div className="flex flex-1 flex-col items-center border-r border-zinc-800 px-4 py-3 last:border-r-0">
      <span className="text-xs uppercase tracking-widest text-zinc-500">
        {label}
      </span>
      <span
        className={`font-mono text-3xl font-semibold tabular-nums ${accent ?? "text-zinc-50"}`}
      >
        {value}
        {unit ? (
          <span className="ml-1 text-base text-zinc-400">{unit}</span>
        ) : null}
      </span>
    </div>
  );
}

export default function StatusBar({ sample }: { sample: Sample | null }) {
  const s = sample;
  const status = s ? (STATUS_LABELS[s.sim_status] ?? String(s.sim_status)) : "--";
  const mode = s ? (MODE_LABELS[s.control_mode] ?? String(s.control_mode)) : "--";

  const statusAccent = !s
    ? "text-zinc-50"
    : s.sim_status === 2
      ? "text-red-400"
      : s.sim_status === 1
        ? "text-green-400"
        : "text-zinc-300";

  return (
    <div className="flex flex-wrap items-stretch rounded-lg border border-zinc-800 bg-zinc-900">
      <Field label="RPM" value={fmt(s?.rpm)} accent="text-amber-300" />
      <Field
        label="Torque"
        value={fmt(s?.torque_ftlbs, 1)}
        unit="ft-lbs"
        accent="text-cyan-300"
      />
      <Field label="HP" value={fmt(s?.hp, 1)} accent="text-pink-300" />
      <Field label="Valve" value={fmt(s?.valve_pct, 1)} unit="%" />
      <Field label="Mode" value={mode} />
      <Field label="Status" value={status} accent={statusAccent} />
      {s?.limiter_active === 1 ? (
        <Field label="Limiter" value="CUT" accent="text-red-400" />
      ) : null}
    </div>
  );
}
