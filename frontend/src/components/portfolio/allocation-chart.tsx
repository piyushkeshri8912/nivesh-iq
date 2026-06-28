"use client";

import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import { SectorExposure } from "@/lib/api";

interface AllocationChartProps {
  sectors: SectorExposure[];
}

const SPECIAL_SECTOR_COLORS: Record<string, string> = {
  gold: "#F5B301",
  silver: "#B9C2C9",
};

const BLUE_FAMILY = [
  "#1D4ED8",
  "#2563EB",
  "#3B82F6",
  "#5B84D1",
  "#6A95E4",
  "#88A9EB",
];

const KEYWORD_COLOR_MAP: Array<{ keywords: string[]; color: string }> = [
  { keywords: ["equity", "stock", "stocks"], color: "#1D4ED8" },
  { keywords: ["technology", "tech", "it"], color: "#2563EB" },
  { keywords: ["financial", "finance", "bank"], color: "#5B84D1" },
  { keywords: ["etf"], color: "#6A95E4" },
  { keywords: ["debt", "bond", "bonds"], color: "#88A9EB" },
  { keywords: ["cash", "liquid"], color: "#94A3B8" },
];

const hashString = (str: string) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
    hash |= 0;
  }
  return Math.abs(hash);
};

const getSectorColor = (sector: string) => {
  const normalized = sector.trim().toLowerCase();

  if (SPECIAL_SECTOR_COLORS[normalized]) {
    return SPECIAL_SECTOR_COLORS[normalized];
  }

  for (const rule of KEYWORD_COLOR_MAP) {
    if (rule.keywords.some((keyword) => normalized.includes(keyword))) {
      return rule.color;
    }
  }

  return BLUE_FAMILY[hashString(normalized) % BLUE_FAMILY.length];
};

export default function AllocationChart({ sectors }: AllocationChartProps) {
  if (sectors.length === 0) {
    return (
      <div className="h-64 flex items-center justify-center border border-zinc-800 rounded-2xl text-zinc-400 bg-zinc-950/60">
        No asset allocations calculated.
      </div>
    );
  }

  const chartData = [...sectors].sort((a, b) => b.value - a.value);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      const color = getSectorColor(data.sector);

      return (
        <div className="bg-zinc-950 border border-zinc-800 p-3.5 rounded-xl shadow-xl shadow-black/30 space-y-1">
          <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">
            {data.sector}
          </p>

          <div className="space-y-0.5">
            <p className="text-sm font-bold text-zinc-100">
              Value:{" "}
              <span className="font-mono">
                ₹{data.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </p>
            <p className="text-xs font-semibold" style={{ color }}>
              Ratio: <span className="font-mono">{data.percentage.toFixed(1)}%</span>
            </p>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-baseline">
        <h3 className="text-lg font-bold text-zinc-100">Sector Exposure</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 items-start">
        <div className="h-56 w-full relative flex items-center justify-center">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={92}
                paddingAngle={2}
                dataKey="value"
                nameKey="sector"
                stroke="#111827"
                strokeWidth={2}
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getSectorColor(entry.sector)} />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>

          <div className="absolute flex flex-col items-center justify-center pointer-events-none">
            <span className="text-[10px] text-zinc-400 font-semibold uppercase tracking-wider">
              Sectors
            </span>
            <span className="text-2xl font-black text-zinc-100 mt-0.5">
              {chartData.length}
            </span>
          </div>
        </div>

        <div className="w-full min-h-0 md:pl-2">
          <div className="space-y-2">
            {chartData.map((entry) => {
              const color = getSectorColor(entry.sector);

              return (
                <div
                  key={entry.sector}
                  className="flex justify-between items-center py-2 border-b border-zinc-800/70 hover:bg-zinc-900/60 px-2 rounded-lg transition-colors text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0 ring-1 ring-black/20"
                      style={{ backgroundColor: color }}
                    />
                    <span className="font-semibold text-zinc-200 truncate">
                      {entry.sector}
                    </span>
                  </div>

                  <span className="font-bold text-zinc-100 font-mono ml-4 shrink-0">
                    {entry.percentage.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}