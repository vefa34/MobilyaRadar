"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function Reviews() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api("/api/companies/reviews").then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  async function decide(id: string, decision: string) {
    try { await api(`/api/companies/reviews/${id}`, { method: "POST", json: { decision } }); load(); } catch (e: any) { setError(e.message); }
  }
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">Duplicate review</h1>
      <p className="text-sm muted">Low-confidence matches are never merged automatically. Decide: same company (merge), same group/branch (link), or different companies.</p>
      <ErrorBox error={error} />
      {rows?.map((r) => (
        <div key={r.id} className="card text-sm">
          <div className="mb-2 text-xs muted">match score {Math.round(r.score * 100)}% · {r.reasons.join("; ")} · suggested: {r.relation}</div>
          <div className="grid gap-2 sm:grid-cols-2">{[r.a, r.b].map((c: any) => (
            <div key={c.id} className="rounded-lg border border-slate-200 p-2 dark:border-slate-800" dir="auto">
              <a className="font-semibold underline" href={`/companies/${c.id}`}>{c.name}</a>
              <div className="text-xs muted">{c.city ?? "–"} · {c.domain ?? "no website"} · {c.phone ?? "no phone"}</div></div>))}</div>
          <div className="mt-2 flex gap-2"><button className="btn" onClick={() => decide(r.id, "merge")}>Merge</button>
            <button className="btn-ghost" onClick={() => decide(r.id, "group")}>Link as group/branch</button>
            <button className="btn-ghost" onClick={() => decide(r.id, "reject")}>Different companies</button></div>
        </div>))}
      {rows && !rows.length && <div className="card text-sm muted">Nothing to review.</div>}
    </div>
  );
}
