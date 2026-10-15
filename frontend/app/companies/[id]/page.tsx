"use client";
import { useEffect, useState } from "react";
import { api, BUYER_LABELS, PRIORITY_LABELS } from "@/lib/api";
import { Badge, BarList, ErrorBox, Score, SyntheticBanner } from "@/components/ui";

const COMPONENT_LABELS: Record<string, string> = { product_fit: "Product fit (25%)", buyer_role: "Buyer role (20%)", import_evidence: "Import evidence (20%)",
  commercial_scale: "Commercial scale (15%)", market_logistics: "Market & logistics (10%)", accessibility: "Accessibility (10%)" };

export default function CompanyDetail({ params }: { params: { id: string } }) {
  const [d, setD] = useState<any>(null);
  const [lead, setLead] = useState({ crm_status: "new", notes: "", sales_outcome: "" });
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const load = () => api(`/api/companies/${params.id}`).then((x) => {
    setD(x);
    if (x.lead) setLead({ crm_status: x.lead.crm_status, notes: x.lead.notes ?? "", sales_outcome: x.lead.sales_outcome ?? "" });
  }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []); // eslint-disable-line

  async function save() {
    try {
      await api(`/api/companies/${params.id}/lead`, { method: "PATCH", json: { crm_status: lead.crm_status, notes: lead.notes, sales_outcome: lead.sales_outcome || null } });
      setSaved(true); setTimeout(() => setSaved(false), 1500);
    } catch (e: any) { setError(e.message); }
  }
  if (error) return <ErrorBox error={error} />;
  if (!d) return <div className="muted">Loading…</div>;
  const c = d.company;
  const comps = d.score?.components?.fit ?? {};
  return (
    <div className="space-y-4">
      <SyntheticBanner show={c.is_synthetic} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold" dir="auto">{c.display_name}</h1>
          {c.name_transliterated && <div className="muted">{c.name_transliterated}</div>}
          {c.legal_name && <div className="text-sm">Legal name: {c.legal_name}</div>}
          <div className="mt-1 flex flex-wrap gap-2 text-sm">
            <Badge tone={c.research_status}>{c.research_status}</Badge>
            {c.buyer_types.map((t: string) => <Badge key={t}>{BUYER_LABELS[t] ?? t}</Badge>)}
            <Badge tone={c.import_activity_status === "verified" ? "verified" : undefined}>{`import: ${c.import_activity_status}`}</Badge>
          </div>
          {c.rejection_reason && <div className="mt-1 text-sm text-red-700 dark:text-red-300">Rejected: {c.rejection_reason}</div>}
        </div>
        <div className="grid grid-cols-2 gap-3 text-center">
          <div className="card"><div className="label">Buyer fit</div><div className="text-3xl"><Score value={c.buyer_fit_score} /></div></div>
          <div className="card"><div className="label">Data confidence</div><div className="text-3xl"><Score value={c.data_confidence_score} /></div></div>
          <div className="col-span-2 text-sm muted">{PRIORITY_LABELS[c.priority] ?? c.priority}</div>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <div className="card space-y-1 text-sm">
          <h2 className="font-semibold">Company</h2>
          <div>Country / city: <span dir="auto">{c.country} / {c.city ?? "unknown"}</span></div>
          <div dir="auto">Address: {c.address ?? "unknown"}</div>
          <div>Website: {c.website ? <a className="underline" href={c.website} target="_blank" rel="noreferrer">{c.website}</a> : "unknown"} {c.website_status && <span className="muted">({c.website_status})</span>}</div>
          <div>Email: {c.general_email ?? "unknown"}</div><div>Phone: {c.phone ?? "unknown"}</div>
          <div>Registration: {c.registration_number ?? "unknown"} · VAT: {c.vat_number ?? "unknown"}</div>
          <div>Stores: {c.store_count ?? "unknown"} · Products: {c.product_categories.join(", ") || "unknown"}</div>
          <div>Website product match: {c.website_product_match != null ? `${Math.round(c.website_product_match * 100)}%` : "unknown"}</div>
          <div>Last verified: {c.last_verified_at ? new Date(c.last_verified_at).toLocaleDateString() : "never"}</div>
        </div>
        <div className="card text-sm">
          <h2 className="mb-2 font-semibold">Why this score</h2>
          <BarList data={Object.entries(comps).map(([k, v]) => ({ label: COMPONENT_LABELS[k] ?? k, value: Math.round((v as number) * 100) }))} format={(v) => `${v}%`} />
          <ul className="mt-2 list-inside list-disc space-y-0.5 text-xs">{d.score?.explanation?.map((e: any, i: number) => <li key={i}><b>{e.component}</b>: {e.text}</li>)}</ul>
          {d.score && <div className="mt-1 text-xs muted">weights {d.score.weights_version} · {new Date(d.score.computed_at).toLocaleString()}</div>}
        </div>
        <div className="card space-y-2 text-sm">
          <h2 className="font-semibold">CRM</h2>
          <select aria-label="CRM status" className="input" value={lead.crm_status} onChange={(e) => setLead({ ...lead, crm_status: e.target.value })}>
            {["new", "qualified", "contacted", "in_discussion", "customer", "not_interested", "do_not_contact"].map((s) => <option key={s}>{s}</option>)}</select>
          <select aria-label="Sales outcome" className="input" value={lead.sales_outcome} onChange={(e) => setLead({ ...lead, sales_outcome: e.target.value })}>
            <option value="">outcome: –</option><option value="won">won</option><option value="lost">lost</option><option value="no_response">no response</option></select>
          <textarea aria-label="Notes" className="input min-h-[80px]" placeholder="Notes" value={lead.notes} onChange={(e) => setLead({ ...lead, notes: e.target.value })} />
          <button className="btn" onClick={save}>{saved ? "Saved ✓" : "Save"}</button>
          <p className="text-xs muted">Outcomes feed score calibration (Dashboard → calibration API).</p>
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">Contacts</h2>
          <table className="table"><thead><tr><th>Type</th><th>Value</th><th>Dept.</th><th>Source</th><th>Observed</th></tr></thead>
            <tbody>{d.contacts.map((x: any) => (
              <tr key={x.id}><td>{x.type}{x.do_not_contact && " ⛔"}</td><td>{x.person ? `${x.person} – ` : ""}{x.value}{x.title && <div className="text-xs muted">{x.title}</div>}</td>
                <td>{x.department}</td><td className="text-xs">{x.url ? <a className="underline" href={x.url} target="_blank" rel="noreferrer">{x.source.name}</a> : x.source.name}</td>
                <td className="text-xs">{new Date(x.observed_at).toLocaleDateString()}</td></tr>))}</tbody></table>
          {!d.contacts.length && <div className="text-sm muted">No business contacts found yet.</div>}</div>
        <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">Locations & aliases</h2>
          <ul className="space-y-1 text-sm">{d.locations.map((l: any, i: number) => (
            <li key={i} dir="auto"><Badge>{l.type}</Badge> {l.address ?? l.city} <span className="text-xs muted">({l.source.name}{l.retention_until ? `, retained until ${new Date(l.retention_until).toLocaleDateString()}` : ""})</span></li>))}</ul>
          <div className="mt-2 flex flex-wrap gap-1 text-xs">{d.aliases.map((a: any, i: number) => <span key={i} dir="auto" className="rounded bg-slate-100 px-2 py-0.5 dark:bg-slate-800">{a.alias} <span className="muted">{a.script}</span></span>)}</div></div>
      </div>

      {d.import_signals.length > 0 && (
        <div className="card text-sm"><h2 className="mb-2 font-semibold">Import signals</h2>
          <ul className="space-y-1">{d.import_signals.map((s: any, i: number) => (
            <li key={i}><Badge tone={s.verified ? "verified" : undefined}>{s.verified ? "verified" : "unverified"}</Badge> {s.type}: {s.description}
              {s.url && <> — <a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.source.name}</a></>}</li>))}</ul></div>)}

      <div className="card overflow-x-auto"><h2 className="mb-2 font-semibold">Evidence ({d.evidence.length})</h2>
        <table className="table"><thead><tr><th>Field</th><th>Value / snippet</th><th>Type</th><th>Source</th><th>Observed</th></tr></thead>
          <tbody>{d.evidence.map((e: any, i: number) => (
            <tr key={i}><td className="text-xs">{e.field}</td><td className="max-w-md text-xs" dir="auto">{e.value}{e.snippet && <div className="muted">“{e.snippet}”</div>}</td>
              <td className="text-xs">{e.type}</td>
              <td className="text-xs">{e.url ? <a className="underline" href={e.url} target="_blank" rel="noreferrer">{e.source.name}</a> : e.source.name}
                {!e.source.export_allowed && <div className="muted">not exportable</div>}</td>
              <td className="text-xs">{new Date(e.observed_at).toLocaleDateString()}</td></tr>))}</tbody></table></div>
    </div>
  );
}
