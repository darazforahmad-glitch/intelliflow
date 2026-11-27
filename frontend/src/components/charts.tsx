"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Point {
  label: string;
  date: string;
  hours: number;
}

export function HoursSavedChart({ data }: { data: Point[] }) {
  const longPeriod = data.length > 10;
  return (
    <div
      className="h-64 w-full"
      role="img"
      aria-label={`Hours saved per day: ${data.map((d) => `${d.date} ${d.hours} h`).join(", ")}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey={longPeriod ? "date" : "label"}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#475569", fontSize: 12 }}
            interval={longPeriod ? 4 : 0}
            tickFormatter={(value: string) => (longPeriod ? value.slice(0, 5) : value)}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#475569", fontSize: 12 }}
            domain={[0, (max: number) => Math.max(1, Math.ceil(max))]}
            tickCount={5}
            tickFormatter={(v: number) => `${v}`}
          />
          <Tooltip
            cursor={{ fill: "#eef2ff" }}
            formatter={(value) => [`${value} h`, "Hours saved"]}
            labelFormatter={(_, payload) => (payload?.[0]?.payload as Point | undefined)?.date ?? ""}
            contentStyle={{ borderRadius: 12, borderColor: "#e2e8f0" }}
          />
          <Bar dataKey="hours" fill="#10b981" radius={[6, 6, 0, 0]} maxBarSize={44} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RunsChart({ data }: { data: { date: string; runs: number; failed: number }[] }) {
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#475569", fontSize: 11 }}
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#475569", fontSize: 12 }}
            allowDecimals={false}
          />
          <Tooltip contentStyle={{ borderRadius: 12, borderColor: "#e2e8f0" }} />
          <Bar dataKey="runs" name="Runs" stackId="a" fill="#6366f1" />
          <Bar dataKey="failed" name="Failed" stackId="a" fill="#ef4444" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
