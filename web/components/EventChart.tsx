"use client"

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts"
import type { ChartPoint } from "@/lib/api"

interface EventChartProps {
  data: ChartPoint[]
}

export default function EventChart({ data }: EventChartProps) {
  return (
    <div className="glass-card mx-4 mt-4 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="section-label mb-0">Event Volume — Last 24h</span>
        <span className="text-text-dim text-xs font-mono">
          {data.reduce((s, d) => s + d.count, 0)} total
        </span>
      </div>
      <div className="h-20">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-text-dim text-xs font-mono">
            No data yet — run a collection first
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 2, right: 4, bottom: 0, left: -24 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#1e2535"
                vertical={false}
              />
              <XAxis
                dataKey="hour"
                tick={{ fill: "#64748b", fontSize: 10, fontFamily: "monospace" }}
                axisLine={false}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 10, fontFamily: "monospace" }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                contentStyle={{
                  background: "#141820",
                  border: "1px solid #1e2535",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontFamily: "monospace",
                  color: "#e2e8f0",
                }}
                labelStyle={{ color: "#64748b" }}
                cursor={{ stroke: "#3b82f6", strokeWidth: 1, strokeDasharray: "3 3" }}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3, fill: "#3b82f6", strokeWidth: 0 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
