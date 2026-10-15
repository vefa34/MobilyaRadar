"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { Badge, BarList, ErrorBox, StatTile } from "@/components/ui";

const ACTIVE = ["queued", "planning", "discovering", "enriching", "scoring"];

export default function JobMonitor({ params }: { params: { id: string } }) {
  const [mon, setMon] = useState<any>(null);
  const [cov, setCov] = useState<any>(null);
  const [manual, setManual] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"progress" | "coverage" | "manual">("progress");

  const load = useCallback(async () => {
    try {
      const m = await api(`/api/research/jobs/${params.id}/monitor`);
      setMon(m);
      if (!ACTIVE.includes(m.job.status) || !cov) setCov(await api(`/api/research/jobs/${params.id}/coverage?refresh=${ACTIVE.includes(m.job.status)}`));
    } catch (e: any) { setError(e.message); }
  }, [params.id, cov]);

  useEffect(() => { load(); api(`/api/research/jobs/${params.id}/manual-queue`).then(setManual).catch(() => {}); }, []); // eslint-disable-line
  useEffect(() => {
    if (!mon || !ACTIVE.includes(mon.job.status)) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [mon, load]);

  if (error) return <ErrorBox error={error} />;
  if (!mon) return <div className="muted">Loading…</div>;
  const job = mon.job;
  const active = ACTIVE.includes(job.status);
  const sources = Object.entries(mon.by_source as Record<string, any>);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-semibold">{job.name}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm"><Badge>{job.status}</Badge>
            <span className="muted">{job.progress?.phase && active ? `phase: ${job.progress.phase}` : job.stop_reason}</span></div></div>
        <div className="flex gap-2">
          {active && <button className="btn-ghost" onClick={() => api(`/api/research/jobs/${job.id}/cancel`, { method: "POST" }).then(load)}>Cancel</button>}
          {["failed", "cancelled", "draft"].includes(job.status) && <button className="btn" onClick={() => api(`/api/research/jobs/${job.id}/start`, { method: "POST" }).then(load)}>Start</button>}
          <Link className="btn-ghost" href={`/companies?job_id=${job.id}`}>Companies</Link>
          <button className="btn-ghost" onClick={() => download(`/api/exports/companies?format=xlsx&job_id=${job.id}`, "leads.xlsx")}>Export XLSX</button>
        </div>
      </div>
      {job.error && <ErrorBox error={job.error} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Unique companies" value={cov?.unique_companies ?? job.progress?.unique_companies ?? 0} hint={cov ? `${cov.raw_records} raw records` : undefined} />
        <StatTile label="Qualified (real)" value={cov?.qualified_real ?? "–"} hint={`fit ≥ ${job.min_buyer_fit}`} />
        <StatTile label="Plan cells done" value={job.progress?.tasks_done ?? 0} hint={`${job.plan_summary?.cells ?? "?"} planned`} />
        <StatTile label="Spent" value={`$${job.spent_usd.toFixed(3)}`} hint={`budget $${job.budget_usd}`} />
        <StatTile label="Cost / qualified lead" value={cov?.cost_per_qualified_lead_usd != null ? `$${cov.cost_per_qualified_lead_usd}` : "–"} />
      </div>
      <div className="flex gap-2 border-b border-slate-200 dark:border-slate-800">
        {(["progress", "coverage", "manual"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand font-semibold" : "muted"}`}>
            {t === "manual" ? `Manual queue (${manual.length})` : t[0].toUpperCase() + t.slice(1)}</button>))}
      </div>

      {tab === "progress" && (
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="card"><h2 className="mb-2 font-semibold">New unique companies by country</h2>
            <BarList data={Object.entries(mon.by_country as Record<string, any>).map(([k, v]) => ({ label: k, value: v.new_unique }))} /></div>
          <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">By source</h2>
            <table className="table"><thead><tr><th>Source</th><th>Cells</th><th>Raw</th><th>New</th><th>Cost</th><th>Statuses</th></tr></thead>
              <tbody>{sources.map(([k, v]) => (
                <tr key={k}><td>{k}</td><td className="tabular-nums">{v.tasks}</td><td className="tabular-nums">{v.raw}</td><td className="tabular-nums">{v.new_unique}</td>
                  <td className="tabular-nums">${v.cost_usd}</td>
                  <td><div className="flex flex-wrap gap-1">{Object.entries(v.statuses as Record<string, number>).map(([s, n]) => <Badge key={s} tone={s}>{`${s} ${n}`}</Badge>)}</div></td></tr>))}
              </tbody></table></div>
          <div className="card lg:col-span-2 overflow-x-auto"><h2 className="mb-2 font-semibold">Recent queries</h2>
            <table className="table"><thead><tr><th>Source</th><th>Query</th><th>Lang</th><th>Page</th><th>Results</th><th>New</th></tr></thead>
              <tbody>{mon.recent_queries.map((q: any, i: number) => (
                <tr key={i}><td>{q.source}</td><td dir="auto">{q.query}</td><td>{q.language}</td><td>{q.page}</td><td className="tabular-nums">{q.results}</td><td className="tabular-nums">{q.new}</td></tr>))}</tbody></table></div>
          {mon.errors.length > 0 && (
            <div className="card lg:col-span-2 overflow-x-auto"><h2 className="mb-2 font-semibold">Errors & restricted sources</h2>
              <table className="table"><thead><tr><th>Source</th><th>Country</th><th>Status</th><th>Reason</th></tr></thead>
                <tbody>{mon.errors.map((e: any, i: number) => (
                  <tr key={i}><td>{e.source}</td><td>{e.country}{e.city ? ` / ${e.city}` : ""}</td><td><Badge>{e.status}</Badge></td><td className="text-xs">{e.reason}</td></tr>))}</tbody></table></div>)}
        </div>
      )}

      {tab === "coverage" && cov && (
        <div className="space-y-3">
          {cov.warnings.length > 0 && (
            <div className="card border-amber-300 dark:border-amber-700"><h2 className="mb-2 font-semibold">⚠ Coverage warnings</h2>
              <ul className="list-inside list-disc text-sm">{cov.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul></div>)}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="Countries researched" value={`${cov.countries_researched}/${cov.countries_requested}`} />
            <StatTile label="Cities searched" value={cov.cities_searched} />
            <StatTile label="Local-language queries" value={cov.local_language_queries} hint={cov.languages.join(", ")} />
            <StatTile label="Duplicate rate" value={`${Math.round(cov.duplicate_rate * 100)}%`} />
            <StatTile label="Product-verified" value={cov.product_verified} hint="real companies only" />
            <StatTile label="Importers verified / claimed" value={`${cov.importers_verified} / ${cov.importers_claimed}`} hint="real companies only" />
            <StatTile label="With contact info" value={cov.contact_enriched} />
            <StatTile label="Registry-verified" value={cov.registry_verified} />
          </div>
          <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">By country</h2>
            <table className="table"><thead><tr><th>Country</th><th>Cities</th><th>Sources used</th><th>Unavailable</th><th>Unique</th><th>Synthetic</th><th>Relevant (real)</th><th>Qualified (real)</th><th>Gaps</th></tr></thead>
              <tbody>{Object.entries(cov.by_country as Record<string, any>).map(([iso, c]) => (
                <tr key={iso}><td>{c.country}</td><td className="text-xs" dir="auto">{c.cities_searched.length}/{c.cities_planned}: {c.cities_searched.join(", ")}</td>
                  <td className="text-xs">{c.sources_used.join(", ") || "–"}</td>
                  <td className="text-xs">{[...c.sources_restricted, ...c.sources_manual.map((s: string) => s + " (manual)"), ...c.paid_sources_disabled.map((s: string) => s + " (paid off)")].join(", ") || "–"}</td>
                  <td className="tabular-nums">{c.unique_companies}</td><td className="tabular-nums">{c.synthetic_companies}</td><td className="tabular-nums">{c.relevant_companies}</td><td className="tabular-nums">{c.qualified_companies}</td>
                  <td className="text-xs">{c.gaps.join("; ") || "–"}</td></tr>))}</tbody></table></div>
          <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">Source performance</h2>
            <table className="table"><thead><tr><th>Source</th><th>Queries</th><th>Raw</th><th>New unique</th><th>Qualified</th><th>Dup. rate</th><th>Cost</th><th>Errors</th></tr></thead>
              <tbody>{cov.source_performance.map((s: any) => (
                <tr key={s.source}><td>{s.name}</td><td className="tabular-nums">{s.queries}</td><td className="tabular-nums">{s.raw_results}</td><td className="tabular-nums">{s.new_unique}</td>
                  <td className="tabular-nums">{s.qualified}</td><td className="tabular-nums">{Math.round(s.duplicate_rate * 100)}%</td><td className="tabular-nums">${s.cost_usd}</td><td className="tabular-nums">{s.errors}</td></tr>))}</tbody></table></div>
        </div>
      )}

      {tab === "manual" && (
        <div className="space-y-2">{manual.map((m) => (
          <div key={m.id} className="card text-sm"><div className="font-semibold">{m.source}</div><p className="muted">{m.instructions}</p>
            <ul className="mt-1 list-inside list-disc" dir="auto">{m.queries.map((q: string, i: number) => <li key={i}>{q}</li>)}</ul></div>))}
          {!manual.length && <div className="text-sm muted">No manual research items.</div>}</div>
      )}
    </div>
  );
}
