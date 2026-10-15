"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BUYER_LABELS } from "@/lib/api";
import { Badge, BarList, ErrorBox, StatTile, SyntheticBanner } from "@/components/ui";

export default function Dashboard() {
  const [d, setD] = useState<any>(null);
  const [demo, setDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api(`/api/dashboard?include_synthetic=${demo}`).then(setD).catch((e) => setError(e.message)); }, [demo]);
  if (error) return <ErrorBox error={error} />;
  if (!d) return <div className="muted">Loading…</div>;
  const countries = Object.entries(d.by_country as Record<string, number>).map(([label, value]) => ({ label: label || "unknown", value })).sort((a, b) => b.value - a.value);
  const types = Object.entries(d.by_buyer_type as Record<string, number>).map(([k, value]) => ({ label: BUYER_LABELS[k] ?? k, value })).sort((a, b) => b.value - a.value);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> include synthetic demo data ({d.synthetic_companies})
        </label>
      </div>
      <SyntheticBanner show={demo && d.synthetic_companies > 0} />
      {d.total_companies === 0 && !demo && (
        <div className="card text-sm">
          No real companies yet. <Link className="underline" href="/research/new">Start a research job</Link>
          {d.synthetic_companies > 0 && <> — {d.synthetic_companies} synthetic demo records exist (toggle above to view).</>}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Potential customers" value={d.total_companies} hint="unique, non-rejected" />
        <StatTile label="High priority" value={d.high_priority} hint="fit ≥ 75 & confidence ≥ 60" />
        <StatTile label="Avg. buyer fit" value={d.avg_buyer_fit ?? "–"} />
        <StatTile label="Verified importers" value={d.verified_importers} hint="shipment-grade evidence only" />
        <StatTile label="Research spend" value={`$${d.research_spend_usd.toFixed(2)}`} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card"><h2 className="mb-2 font-semibold">Companies by country</h2><BarList data={countries} /></div>
        <div className="card"><h2 className="mb-2 font-semibold">Companies by buyer type</h2><BarList data={types} /></div>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card overflow-x-auto">
          <h2 className="mb-2 font-semibold">Source performance</h2>
          <table className="table"><thead><tr><th>Source</th><th>Calls</th><th>Records</th><th>Errors</th><th>Spend</th></tr></thead>
            <tbody>{d.source_performance.map((s: any) => (
              <tr key={s.source}><td>{s.source}</td><td className="tabular-nums">{s.calls}</td><td className="tabular-nums">{s.records}</td>
                <td className="tabular-nums">{s.errors}</td><td className="tabular-nums">${s.spend_usd.toFixed(3)}</td></tr>))}
            </tbody></table>
          {!d.source_performance.length && <div className="text-sm muted">No source executions yet.</div>}
        </div>
        <div className="card">
          <h2 className="mb-2 font-semibold">Recent research</h2>
          <ul className="space-y-2 text-sm">{d.recent_jobs.map((j: any) => (
            <li key={j.id} className="flex items-center justify-between gap-2">
              <Link className="truncate underline" href={`/research/${j.id}`}>{j.name}</Link>
              <span className="flex items-center gap-2"><span className="muted tabular-nums">{j.unique_companies ?? 0} cos</span><Badge>{j.status}</Badge></span>
            </li>))}</ul>
        </div>
      </div>
    </div>
  );
}
