"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, ErrorBox } from "@/components/ui";

export default function Sources() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [filter, setFilter] = useState({ q: "", tier: "", country: "", pending: false });
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ api_key: "", endpoint: "", license_reference: "", license_confirmed: false, enabled: true });
  const [health, setHealth] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);

  const load = () => api(`/api/sources?include_pending=${filter.pending}${filter.country ? `&country=${filter.country}` : ""}`).then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [filter.pending, filter.country]); // eslint-disable-line

  async function save(key: string) {
    try {
      const body: any = { enabled: form.enabled, license_confirmed: form.license_confirmed, license_reference: form.license_reference || null };
      if (form.api_key) body.api_key = form.api_key;
      if (form.endpoint) body.endpoint = form.endpoint;
      await api(`/api/sources/${key}/permission`, { method: "PUT", json: body });
      setEditing(null); load();
    } catch (e: any) { setError(e.message); }
  }
  async function check(key: string) {
    setHealth({ ...health, [key]: { status: "checking…" } });
    try { const h = await api(`/api/sources/${key}/health`, { method: "POST" }); setHealth((x) => ({ ...x, [key]: h })); }
    catch (e: any) { setHealth((x) => ({ ...x, [key]: { status: "error", message: e.message } })); }
  }
  async function review(key: string, status: string) {
    try { await api(`/api/sources/${key}/review`, { method: "POST", json: { review_status: status } }); load(); } catch (e: any) { setError(e.message); }
  }

  const list = (rows ?? []).filter((s) => (!filter.tier || s.tier === filter.tier) &&
    (!filter.q || `${s.name} ${s.key}`.toLowerCase().includes(filter.q.toLowerCase())));
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Source manager</h1>
      <p className="text-sm muted">Catalogue presence ≠ connected. A source runs automatically only when its connector exists, credentials are set and (for licensed data) the licence is confirmed <i>and</i> a provider adapter is implemented.</p>
      <ErrorBox error={error} />
      <div className="card grid gap-2 sm:grid-cols-4">
        <input aria-label="Search sources" className="input" placeholder="Search" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
        <select aria-label="Tier" className="input" value={filter.tier} onChange={(e) => setFilter({ ...filter, tier: e.target.value })}>
          <option value="">All tiers</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
        <input aria-label="Country filter" className="input" placeholder="Country ISO2" value={filter.country} onChange={(e) => setFilter({ ...filter, country: e.target.value.toUpperCase() })} />
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={filter.pending} onChange={(e) => setFilter({ ...filter, pending: e.target.checked })} /> show auto-discovered (pending review)</label>
      </div>
      <div className="space-y-2">{list.map((s) => (
        <div key={s.key} className="card text-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <div className="font-semibold">{s.name} <span className="muted">· {s.tier} · {s.access_model}</span></div>
              <div className="text-xs muted">{s.purposes.join(", ")} · {s.countries.includes("*") ? "global" : s.countries.join(", ")}{s.url && <> · <a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.url}</a></>}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{s.integration_status}</Badge>
              {s.usable ? <Badge tone="completed">usable</Badge> : <span className="text-xs muted">{s.blocked_reason}</span>}
              {s.review_status === "pending_review" && <><button className="btn-ghost" onClick={() => review(s.key, "approved")}>Approve</button>
                <button className="btn-ghost" onClick={() => review(s.key, "rejected")}>Reject</button></>}
              <button className="btn-ghost" onClick={() => check(s.key)}>Health check</button>
              <button className="btn-ghost" onClick={() => { setEditing(editing === s.key ? null : s.key);
                setForm({ api_key: "", endpoint: s.permission.endpoint ?? "", license_reference: s.permission.license_reference ?? "", license_confirmed: s.permission.license_confirmed, enabled: s.permission.enabled ?? true }); }}>Configure</button>
            </div>
          </div>
          <div className="mt-2 grid gap-1 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <div><span className="muted">Auth:</span> {s.auth_required ?? "none"}</div>
            <div><span className="muted">Pricing:</span> {s.pricing ?? "–"}</div>
            <div><span className="muted">Rate limit:</span> {s.rate_limit ?? "–"}</div>
            <div><span className="muted">Reliability:</span> {Math.round(s.reliability * 100)}%</div>
            <div><span className="muted">Storage/retention:</span> {s.storage_allowed ? (s.max_retention_days ? `${s.max_retention_days} days` : "allowed") : "not allowed"}</div>
            <div><span className="muted">Export:</span> {s.export_allowed ? "allowed" : "not allowed"}</div>
            <div><span className="muted">API key:</span> {s.permission.api_key_masked ?? "–"}</div>
            <div><span className="muted">Usage:</span> {s.stats.executions} calls · ${s.stats.spend_usd} · {s.stats.qualified_companies} qualified</div>
          </div>
          {s.terms_summary && <p className="mt-1 text-xs muted">Terms: {s.terms_summary}</p>}
          {s.notes && <p className="text-xs muted">Notes: {s.notes}</p>}
          {(health[s.key] || s.permission.last_health_status) && (
            <p className="mt-1 text-xs">Last check: <b>{health[s.key]?.status ?? s.permission.last_health_status}</b> {health[s.key]?.message ?? s.permission.last_health_message ?? ""}</p>)}
          {editing === s.key && (
            <div className="mt-2 grid gap-2 border-t border-slate-200 pt-2 dark:border-slate-800 sm:grid-cols-2">
              <input aria-label="API key" className="input" type="password" placeholder="API key (stored encrypted)" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
              <input aria-label="Endpoint" className="input" placeholder="Custom endpoint (optional)" value={form.endpoint} onChange={(e) => setForm({ ...form, endpoint: e.target.value })} />
              <input aria-label="Licence reference" className="input" placeholder="Licence / contract reference" value={form.license_reference} onChange={(e) => setForm({ ...form, license_reference: e.target.value })} />
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-1"><input type="checkbox" checked={form.license_confirmed} onChange={(e) => setForm({ ...form, license_confirmed: e.target.checked })} /> licence confirmed</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> enabled</label>
                <button className="btn" onClick={() => save(s.key)}>Save</button>
              </div>
            </div>)}
        </div>))}</div>
    </div>
  );
}
