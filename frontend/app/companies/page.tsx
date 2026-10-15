"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, BUYER_LABELS, download, PRIORITY_LABELS } from "@/lib/api";
import { Badge, ErrorBox, Score, SyntheticBanner } from "@/components/ui";

function CompaniesInner() {
  const sp = useSearchParams();
  const [f, setF] = useState({ q: "", country: "", buyer_type: "", min_fit: "", min_confidence: "", import_status: "", crm_status: "",
    sort: "fit", include_synthetic: false, include_rejected: false, job_id: sp.get("job_id") ?? "" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const p = new URLSearchParams({ page: String(page), page_size: "50", sort: f.sort });
    for (const k of ["q", "country", "buyer_type", "min_fit", "min_confidence", "import_status", "crm_status", "job_id"] as const) if (f[k]) p.set(k, f[k]);
    if (f.include_synthetic) p.set("include_synthetic", "true");
    if (f.include_rejected) p.set("include_rejected", "true");
    const t = setTimeout(() => api(`/api/companies?${p}`).then(setData).catch((e) => setError(e.message)), 200);
    return () => clearTimeout(t);
  }, [f, page]);

  const set = (k: string, v: any) => { setPage(1); setF({ ...f, [k]: v }); };
  async function exportSel(fmt: "csv" | "xlsx") {
    const p = new URLSearchParams({ format: fmt });
    sel.forEach((id) => p.append("ids", id));
    if (f.include_synthetic) p.set("include_synthetic", "true");
    try { const r = await download(`/api/exports/companies?${p}`, `leads.${fmt}`); setMsg(`Exported ${r.rows} rows; ${r.withheld} fields withheld by source licences.`); }
    catch (e: any) { setError(e.message); }
  }
  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Companies</h1>
      <ErrorBox error={error} />
      {msg && <div className="text-sm muted">{msg}</div>}
      <SyntheticBanner show={f.include_synthetic} />
      <div className="card grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <input aria-label="Search" className="input lg:col-span-2" placeholder="Search name / domain / alias" value={f.q} onChange={(e) => set("q", e.target.value)} />
        <input aria-label="Country" className="input" placeholder="Country (ISO2)" value={f.country} onChange={(e) => set("country", e.target.value.toUpperCase())} />
        <select aria-label="Buyer type" className="input" value={f.buyer_type} onChange={(e) => set("buyer_type", e.target.value)}>
          <option value="">All buyer types</option>{Object.entries(BUYER_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <input aria-label="Min fit" className="input" type="number" placeholder="Min fit" value={f.min_fit} onChange={(e) => set("min_fit", e.target.value)} />
        <input aria-label="Min confidence" className="input" type="number" placeholder="Min confidence" value={f.min_confidence} onChange={(e) => set("min_confidence", e.target.value)} />
        <select aria-label="Import status" className="input" value={f.import_status} onChange={(e) => set("import_status", e.target.value)}>
          <option value="">Any import status</option><option value="verified">verified</option><option value="claimed">claimed</option><option value="unknown">unknown</option></select>
        <select aria-label="CRM status" className="input" value={f.crm_status} onChange={(e) => set("crm_status", e.target.value)}>
          <option value="">Any CRM status</option>{["new", "qualified", "contacted", "in_discussion", "customer", "not_interested", "do_not_contact"].map((s) => <option key={s}>{s}</option>)}</select>
        <select aria-label="Sort" className="input" value={f.sort} onChange={(e) => set("sort", e.target.value)}>
          <option value="fit">Sort: buyer fit</option><option value="confidence">Sort: confidence</option><option value="name">Sort: name</option><option value="recent">Sort: newest</option></select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.include_synthetic} onChange={(e) => set("include_synthetic", e.target.checked)} /> synthetic</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.include_rejected} onChange={(e) => set("include_rejected", e.target.checked)} /> rejected</label>
        {f.job_id && <button className="btn-ghost" onClick={() => set("job_id", "")}>Job filter ✕</button>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="muted">{data?.total ?? 0} companies · {sel.length} selected</span>
        <button className="btn-ghost" disabled={!sel.length} onClick={() => exportSel("xlsx")}>Export selected (XLSX)</button>
        <button className="btn-ghost" disabled={!sel.length} onClick={() => exportSel("csv")}>CSV</button>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="table">
          <thead><tr><th><input aria-label="Select all" type="checkbox" checked={!!data?.items.length && sel.length === data.items.length}
            onChange={(e) => setSel(e.target.checked ? data!.items.map((i) => i.id) : [])} /></th>
            <th>Company</th><th>Country / city</th><th>Buyer type</th><th>Fit</th><th>Conf.</th><th>Priority</th><th>Import</th><th>Contact</th><th>Sources</th><th>CRM</th></tr></thead>
          <tbody>{data?.items.map((c) => (
            <tr key={c.id}>
              <td><input aria-label={`Select ${c.display_name}`} type="checkbox" checked={sel.includes(c.id)} onChange={() => setSel(sel.includes(c.id) ? sel.filter((x) => x !== c.id) : [...sel, c.id])} /></td>
              <td><Link className="font-medium underline" href={`/companies/${c.id}`} dir="auto">{c.display_name}</Link>
                {c.name_transliterated && <div className="text-xs muted">{c.name_transliterated}</div>}
                {c.website && <div className="text-xs muted">{c.website.replace(/^https?:\/\//, "")}</div>}</td>
              <td dir="auto">{c.country} {c.city && <span className="muted">/ {c.city}</span>}</td>
              <td>{BUYER_LABELS[c.primary_buyer_type] ?? c.primary_buyer_type}</td>
              <td><Score value={c.buyer_fit_score} /></td><td><Score value={c.data_confidence_score} /></td>
              <td className="text-xs">{PRIORITY_LABELS[c.priority] ?? c.priority}</td>
              <td><Badge tone={c.import_activity_status === "verified" ? "verified" : undefined}>{c.import_activity_status}</Badge></td>
              <td className="text-xs">{c.general_email ?? ""}{c.general_email && c.phone ? <br /> : null}{c.phone ?? ""}</td>
              <td className="tabular-nums">{c.source_count}</td><td className="text-xs">{c.crm_status}</td>
            </tr>))}</tbody>
        </table>
        {data && !data.items.length && <div className="p-4 text-sm muted">No companies match. {!f.include_synthetic && "Synthetic demo data is hidden."}</div>}
      </div>
      <div className="flex items-center gap-2 text-sm">
        <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
        <span className="tabular-nums">{page} / {pages}</span>
        <button className="btn-ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

export default function Companies() {
  return <Suspense fallback={<div className="muted">Loading…</div>}><CompaniesInner /></Suspense>;
}
