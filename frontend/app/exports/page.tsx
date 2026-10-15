"use client";
import { useEffect, useState } from "react";
import { api, download } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function Exports() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [f, setF] = useState({ job_id: "", min_fit: "50", include_synthetic: false });
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api("/api/research/jobs").then(setJobs).catch((e) => setError(e.message)); }, []);

  async function go(fmt: "csv" | "xlsx") {
    setError(null);
    const p = new URLSearchParams({ format: fmt });
    if (f.job_id) p.set("job_id", f.job_id);
    if (f.min_fit) p.set("min_fit", f.min_fit);
    if (f.include_synthetic) p.set("include_synthetic", "true");
    try {
      const r = await download(`/api/exports/companies?${p}`, `leads.${fmt}`);
      setResult(`Exported ${r.rows} companies. ${r.withheld} field values withheld and ${r.excluded} companies excluded because their only source forbids export.`);
    } catch (e: any) { setError(e.message); }
  }
  return (
    <div className="max-w-3xl space-y-3">
      <h1 className="text-xl font-semibold">Exports</h1>
      <ErrorBox error={error} />
      <div className="card space-y-3">
        <div><label className="label" htmlFor="job">Research job</label>
          <select id="job" className="input" value={f.job_id} onChange={(e) => setF({ ...f, job_id: e.target.value })}>
            <option value="">All companies</option>{jobs.map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}</select></div>
        <div><label className="label" htmlFor="minfit">Minimum buyer fit</label>
          <input id="minfit" className="input" type="number" value={f.min_fit} onChange={(e) => setF({ ...f, min_fit: e.target.value })} /></div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.include_synthetic} onChange={(e) => setF({ ...f, include_synthetic: e.target.checked })} />
          include synthetic demo records (labelled; never for real outreach)</label>
        <div className="flex gap-2"><button className="btn" onClick={() => go("xlsx")}>Download XLSX</button><button className="btn-ghost" onClick={() => go("csv")}>Download CSV</button></div>
        {result && <div className="text-sm">{result}</div>}
      </div>
      <div className="card text-sm">
        <h2 className="mb-1 font-semibold">CRM-ready columns</h2>
        <p className="muted">Company ID, name, legal name, country, city, address, website, email, phone, purchasing contact, buyer type(s), products, import activity,
          store count, Buyer Fit, Data Confidence, priority, registration/VAT numbers, research & CRM status, sources, evidence URLs, last verified.
          Fields known only from sources whose licence forbids export (e.g. Google Places content) are left empty; do-not-contact leads have contact fields removed.</p>
      </div>
    </div>
  );
}
