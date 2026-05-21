"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChartPoint {
  x: number; // seconds (live: seconds-ago; history: seconds since run start)
  rpm: number;
  torque: number;
  hp: number;
  setpoint?: number;
}

const RPM_COLOR = "#fbbf24"; // amber
const TORQUE_COLOR = "#22d3ee"; // cyan
const HP_COLOR = "#f472b6"; // pink

// Shared chart for the live rolling window and the static history view.
// Left axis = RPM; right axis = torque (ft-lbs) + HP. High-contrast colors and
// large strokes so it reads at a glance from 1-2 m in a shop/trailer.
export default function LiveChart({
  points,
  xLabel,
  reversed = false,
  xDomain = ["auto", "auto"],
}: {
  points: ChartPoint[];
  xLabel: string;
  reversed?: boolean;
  xDomain?: [number | "auto", number | "auto"];
}) {
  if (points.length === 0) {
    return (
      <div className="h-96 w-full flex items-center justify-center">
        <p className="text-sm text-zinc-600 uppercase tracking-widest">
          Waiting for data
        </p>
      </div>
    );
  }

  return (
    <div className="h-96 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={points}
          margin={{ top: 8, right: 16, bottom: 24, left: 8 }}
        >
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
          <XAxis
            dataKey="x"
            type="number"
            domain={xDomain}
            reversed={reversed}
            tick={{ fill: "#a1a1aa", fontSize: 12 }}
            stroke="#52525b"
            label={{
              value: xLabel,
              position: "insideBottom",
              offset: -12,
              fill: "#a1a1aa",
              fontSize: 12,
            }}
          />
          <YAxis
            yAxisId="rpm"
            tick={{ fill: RPM_COLOR, fontSize: 12 }}
            stroke={RPM_COLOR}
            width={56}
            label={{
              value: "RPM",
              angle: -90,
              position: "insideLeft",
              fill: RPM_COLOR,
              fontSize: 12,
            }}
          />
          <YAxis
            yAxisId="power"
            orientation="right"
            tick={{ fill: "#a1a1aa", fontSize: 12 }}
            stroke="#52525b"
            width={56}
            label={{
              value: "ft-lbs / HP",
              angle: 90,
              position: "insideRight",
              fill: "#a1a1aa",
              fontSize: 12,
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 6,
              color: "#fafafa",
            }}
            labelStyle={{ color: "#a1a1aa" }}
            isAnimationActive={false}
          />
          <Legend wrapperStyle={{ color: "#e4e4e7" }} />
          <Line
            yAxisId="rpm"
            type="monotone"
            dataKey="rpm"
            name="RPM"
            stroke={RPM_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            yAxisId="rpm"
            type="monotone"
            dataKey="setpoint"
            name="RPM Target"
            stroke="#fbbf24"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            yAxisId="power"
            type="monotone"
            dataKey="torque"
            name="Torque (ft-lbs)"
            stroke={TORQUE_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            yAxisId="power"
            type="monotone"
            dataKey="hp"
            name="HP"
            stroke={HP_COLOR}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
