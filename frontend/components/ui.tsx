"use client";
import React from "react";

export function StatTile({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="card">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs muted">{hint}</div>}
    </div>
  );
}

/** Single-series horizontal bars: one hue, values labelled in text ink, hover title per bar. */
export function BarList({ data, format = (v: number) => String(v), empty = "No data yet" }:
  { data: { label: string; value: number }[]; format?: (v: number) => string; empty?: string }) {
  if (!data.length) return <div className="text-sm muted">{empty}</div>;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <ul className="space-y-[2px]" role="list">
      {data.map((d) => (
        <li key={d.label} className="group grid grid-cols-[minmax(6rem,10rem)_1fr_auto] items-center gap-2 py-1 text-sm"
            title={`${d.label}: ${format(d.value)}`}>
          <span className="truncate">{d.label}</span>
          <span className="h-3 rounded-r bg-slate-100 dark:bg-slate-800">
            <span className="block h-3 rounded-r group-hover:opacity-80"
                  style={{ width: `${(d.value / max) * 100}%`, background: "var(--bar)", minWidth: d.value ? 4 : 0 }} />
          </span>
          <span className="tabular-nums text-slate-600 dark:text-slate-300">{format(d.value)}</span>
        </li>
      ))}
    </ul>
  );
}

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  completed_partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200",
  running: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  discovering: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  enriching: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  scoring: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  planning: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200",
  queued: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
  rate_limited: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  access_restricted: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200",
  manual_review_required: "bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200",
  verified: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200",
};
const STATUS_ICON: Record<string, string> = { completed: "✓", verified: "✓", failed: "✕", rejected: "✕", access_restricted: "⚠", rate_limited: "⏳",
  manual_review_required: "✎", completed_partial: "⚠" };

export function Badge({ children, tone }: { children: React.ReactNode; tone?: string }) {
  const key = tone ?? String(children);
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[key] ?? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"}`}>
      {STATUS_ICON[key] && <span aria-hidden>{STATUS_ICON[key]}</span>}
      {String(children).replaceAll("_", " ")}
    </span>
  );
}

export function Score({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="muted">–</span>;
  const tone = value >= 75 ? "text-emerald-700 dark:text-emerald-300" : value >= 50 ? "text-slate-800 dark:text-slate-100" : "text-slate-500";
  return <span className={`tabular-nums font-semibold ${tone}`}>{Math.round(value)}</span>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">{error}</div>;
}

export function SyntheticBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100">
      ⚠ Showing <b>synthetic demo data</b> ([DEMO] records from the mock connector). These are not real companies and are never exported by default.
      Configure real sources in the Source Manager to get actual leads.
    </div>
  );
}
