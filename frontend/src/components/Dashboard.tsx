import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "motion/react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, LabelList, Line, LineChart, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { ChartSpec, DashboardData } from "../api";
import { cx, ease } from "../lib";
import { IconClose } from "./Icons";

// Categorical slots in fixed order (validated for colour-vision deficiency in both themes — see index.css).
const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
const color = (i: number) => SERIES[i % SERIES.length];

const AXIS = { fill: "var(--c-muted)", fontSize: 12 };

function useFormat(unit: string) {
  const { i18n } = useTranslation();
  return useMemo(() => {
    const nf = new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 2 });
    const compact = new Intl.NumberFormat(i18n.language, { notation: "compact", maximumFractionDigits: 1 });
    const prefix = /^[$€£₴]$/.test(unit);
    const wrap = (s: string) => (unit ? (prefix ? `${unit}${s}` : `${s} ${unit}`) : s);
    return { full: (v: number) => wrap(nf.format(v)), axis: (v: number) => (Math.abs(v) >= 10000 ? compact.format(v) : nf.format(v)) };
  }, [i18n.language, unit]);
}

/** One row per x label, one key per series (s0, s1, …) — the shape Recharts wants. */
function toRows(chart: ChartSpec) {
  const order: string[] = [];
  const rows = new Map<string, Record<string, number | string>>();
  chart.series.forEach((s, si) => s.points.forEach((p) => {
    if (!rows.has(p.x)) { rows.set(p.x, { x: p.x }); order.push(p.x); }
    rows.get(p.x)![`s${si}`] = p.y;
  }));
  return order.map((x) => rows.get(x)!);
}

function Tip({ active, payload, label, names, fmt }: {
  active?: boolean; payload?: { dataKey?: string | number; value?: number; color?: string; name?: string; payload?: { x?: string } }[];
  label?: string; names: string[]; fmt: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 shadow-lg text-[13px]">
      <div className="font-semibold text-ink mb-1">{label ?? payload[0].payload?.x}</div>
      {payload.map((p, i) => {
        const idx = typeof p.dataKey === "string" && p.dataKey.startsWith("s") ? Number(p.dataKey.slice(1)) : i;
        return (
          <div key={i} className="flex items-center gap-2 text-ink-2">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: p.color || color(idx) }} />
            <span className="flex-1">{names[idx] ?? p.name}</span>
            <span className="font-semibold text-ink tabular-nums">{fmt(Number(p.value))}</span>
          </div>
        );
      })}
    </div>
  );
}

function Legend({ items }: { items: { name: string; color: string; value?: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 m-0 p-0 list-none text-[13px] text-ink-2">
      {items.map((it) => (
        <li key={it.name} className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: it.color }} />
          <span>{it.name}</span>{it.value && <span className="font-semibold text-ink tabular-nums">{it.value}</span>}
        </li>
      ))}
    </ul>
  );
}

function Plot({ chart }: { chart: ChartSpec }) {
  const fmt = useFormat(chart.unit);
  const names = chart.series.map((s) => s.name);
  const rows = useMemo(() => toRows(chart), [chart]);
  const tip = <Tooltip content={<Tip names={names} fmt={fmt.full} />} cursor={{ fill: "var(--c-soft)", opacity: 0.7 }} />;
  const grid = <CartesianGrid stroke="var(--c-line)" strokeDasharray="0" vertical={false} />;
  const xAxis = <XAxis dataKey="x" tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--c-line-strong)" }} interval="preserveStartEnd" minTickGap={12} />;
  const yAxis = <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt.axis} width={52} />;
  const margin = { top: 8, right: 12, bottom: 0, left: 0 };

  if (chart.type === "share") {
    const pts = chart.series[0].points;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={pts} dataKey="y" nameKey="x" innerRadius="58%" outerRadius="88%" paddingAngle={1.5}
               stroke="var(--c-surface)" strokeWidth={2} isAnimationActive={false}>
            {pts.map((_, i) => <Cell key={i} fill={color(i)} />)}
          </Pie>
          <Tooltip content={<Tip names={pts.map((p) => p.x)} fmt={fmt.full} />} />
        </PieChart>
      </ResponsiveContainer>
    );
  }
  if (chart.type === "hbar") {
    const sorted = [...chart.series[0].points].sort((a, b) => b.y - a.y);
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={sorted} layout="vertical" margin={{ top: 4, right: 56, bottom: 0, left: 4 }} barCategoryGap={8}>
          <CartesianGrid stroke="var(--c-line)" horizontal={false} />
          <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={fmt.axis} />
          <YAxis type="category" dataKey="x" tick={{ ...AXIS, fill: "var(--c-ink-2)" }} tickLine={false} axisLine={false} width={132} />
          <Tooltip content={<Tip names={[chart.series[0].name]} fmt={fmt.full} />} cursor={{ fill: "var(--c-soft)", opacity: 0.7 }} />
          <Bar dataKey="y" fill={color(0)} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
            <LabelList dataKey="y" position="right" formatter={(v: number) => fmt.full(v)} style={{ fill: "var(--c-ink-2)", fontSize: 12 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }
  if (chart.type === "line") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={margin}>
          {grid}{xAxis}{yAxis}
          <Tooltip content={<Tip names={names} fmt={fmt.full} />} cursor={{ stroke: "var(--c-line-strong)" }} />
          {chart.series.map((_, i) => (
            <Line key={i} dataKey={`s${i}`} stroke={color(i)} strokeWidth={2} type="monotone" connectNulls isAnimationActive={false}
                  dot={rows.length <= 24 ? { r: 3.5, fill: color(i), stroke: "var(--c-surface)", strokeWidth: 2 } : false}
                  activeDot={{ r: 5, stroke: "var(--c-surface)", strokeWidth: 2 }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }
  if (chart.type === "area") {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={margin}>
          {grid}{xAxis}{yAxis}
          <Tooltip content={<Tip names={names} fmt={fmt.full} />} cursor={{ stroke: "var(--c-line-strong)" }} />
          {chart.series.map((_, i) => (
            <Area key={i} dataKey={`s${i}`} stroke={color(i)} strokeWidth={2} fill={color(i)} fillOpacity={0.16} type="monotone"
                  connectNulls isAnimationActive={false} activeDot={{ r: 5, stroke: "var(--c-surface)", strokeWidth: 2 }} />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    );
  }
  const stacked = chart.type === "stacked";
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={margin} barGap={2} barCategoryGap="22%">
        {grid}{xAxis}{yAxis}{tip}
        {chart.series.map((_, i) => (
          <Bar key={i} dataKey={`s${i}`} fill={color(i)} isAnimationActive={false} maxBarSize={40}
               stackId={stacked ? "a" : undefined} radius={stacked ? 0 : [4, 4, 0, 0]}
               stroke={stacked ? "var(--c-surface)" : undefined} strokeWidth={stacked ? 2 : 0} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

function DataTable({ chart }: { chart: ChartSpec }) {
  const fmt = useFormat(chart.unit);
  const rows = toRows(chart);
  return (
    <div className="overflow-auto h-full">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr>
            <th className="text-left font-semibold px-2.5 py-1.5 border-b border-line-strong sticky top-0 bg-surface">{chart.x_label || ""}</th>
            {chart.series.map((s) => <th key={s.name} className="text-right font-semibold px-2.5 py-1.5 border-b border-line-strong sticky top-0 bg-surface">{s.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.x)}>
              <td className="px-2.5 py-1.5 border-b border-line text-ink-2">{r.x}</td>
              {chart.series.map((_, i) => (
                <td key={i} className="px-2.5 py-1.5 border-b border-line text-right tabular-nums">
                  {typeof r[`s${i}`] === "number" ? fmt.full(r[`s${i}`] as number) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartCard({ chart, index }: { chart: ChartSpec; index: number }) {
  const { t } = useTranslation();
  const [table, setTable] = useState(false);
  const fmt = useFormat(chart.unit);
  const share = chart.type === "share";
  const total = share ? chart.series[0].points.reduce((a, p) => a + p.y, 0) : 0;
  const legend = share
    ? chart.series[0].points.map((p, i) => ({ name: p.x, color: color(i), value: `${fmt.full(p.y)}${total ? ` · ${Math.round((p.y / total) * 100)}%` : ""}` }))
    : chart.series.length > 1 ? chart.series.map((s, i) => ({ name: s.name, color: color(i) })) : [];
  const tall = chart.type === "hbar" ? Math.max(220, chart.series[0].points.length * 34 + 40) : 280;
  return (
    <motion.figure initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease, delay: Math.min(index * 0.06, 0.3) }}
                   className={cx("m-0 flex flex-col gap-3 p-5 rounded-[20px] bg-surface border border-line min-w-0", chart.type === "hbar" && chart.series[0].points.length > 8 && "lg:col-span-2")}>
      <figcaption className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="font-bold text-[15px] leading-snug">{chart.title}</div>
          {chart.subtitle && <div className="text-[13px] text-muted">{chart.subtitle}</div>}
        </div>
        <div className="flex p-[3px] rounded-[10px] bg-soft text-xs shrink-0" role="group">
          <button onClick={() => setTable(false)} aria-pressed={!table} className={cx("px-2.5 py-1 rounded-lg cursor-pointer", !table ? "bg-surface font-semibold text-brand-deep" : "text-ink-2")}>{t("analytics.chart")}</button>
          <button onClick={() => setTable(true)} aria-pressed={table} className={cx("px-2.5 py-1 rounded-lg cursor-pointer", table ? "bg-surface font-semibold text-brand-deep" : "text-ink-2")}>{t("analytics.table")}</button>
        </div>
      </figcaption>
      {!table && legend.length > 0 && <Legend items={legend} />}
      <div style={{ height: tall }} className="min-w-0">
        {table ? <DataTable chart={chart} /> : <Plot chart={chart} />}
      </div>
      {(chart.y_label || chart.x_label) && !table && !share && (
        <div className="text-xs text-muted">{[chart.y_label && `↑ ${chart.y_label}`, chart.x_label && `→ ${chart.x_label}`].filter(Boolean).join("   ")}</div>
      )}
      {chart.source && <div className="text-xs text-muted border-t border-line pt-2">{t("analytics.source")}: {chart.source}</div>}
    </motion.figure>
  );
}

export default function Dashboard({ data, onClose }: { data: DashboardData; onClose: () => void }) {
  const { t } = useTranslation();
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-night/50 flex justify-center animate-rise" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={data.title} onClick={(e) => e.stopPropagation()}
           className="viz-root w-full max-w-[1180px] h-full sm:h-[calc(100%-32px)] sm:my-4 sm:rounded-[28px] bg-ground overflow-y-auto shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center justify-between gap-4 px-5 sm:px-8 py-4 bg-ground/95 backdrop-blur border-b border-line">
          <div className="min-w-0">
            <div className="text-xs font-semibold tracking-[0.08em] uppercase text-muted">{t("analytics.title")}</div>
            <h2 className="m-0 text-xl sm:text-2xl font-bold tracking-tight truncate">{data.title}</h2>
          </div>
          <button ref={closeRef} onClick={onClose} aria-label={t("common.close")}
                  className="w-11 h-11 shrink-0 flex items-center justify-center rounded-xl bg-surface border border-line hover:bg-soft cursor-pointer"><IconClose /></button>
        </header>
        <div className="px-5 sm:px-8 py-6 flex flex-col gap-5">
          {data.summary && <p className="m-0 text-[15px] leading-relaxed text-ink-2 max-w-3xl">{data.summary}</p>}
          {data.kpis.length > 0 && (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
              {data.kpis.map((k, i) => (
                <motion.div key={k.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05, duration: 0.4, ease }}
                            className="flex flex-col gap-1 p-4 rounded-2xl bg-surface border border-line">
                  <div className="text-[13px] text-muted">{k.label}</div>
                  <div className="text-[24px] font-bold tracking-tight leading-[1.1] tabular-nums break-words">{k.value}</div>
                  {k.hint && <div className="text-xs text-muted">{k.hint}</div>}
                </motion.div>
              ))}
            </div>
          )}
          <div className={cx("grid gap-4", data.charts.length > 1 ? "lg:grid-cols-2" : "grid-cols-1")}>
            {data.charts.map((c, i) => <ChartCard key={i} chart={c} index={i} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
