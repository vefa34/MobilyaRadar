"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Badge, ErrorBox } from "@/components/ui";

export default function ResearchList() {
  const [jobs, setJobs] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const load = () => api("/api/research/jobs").then(setJobs).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between"><h1 className="text-xl font-semibold">Research jobs</h1>
        <Link href="/research/new" className="btn">New research</Link></div>
      <ErrorBox error={error} />
      <div className="card overflow-x-auto">
        <table className="table"><thead><tr><th>Name</th><th>Countries</th><th>Status</th><th>Unique cos</th><th>Spent / budget</th><th>Created</th></tr></thead>
          <tbody>{jobs?.map((j) => (
            <tr key={j.id}><td><Link className="underline" href={`/research/${j.id}`}>{j.name}</Link></td><td>{j.countries.join(", ")}</td>
              <td><Badge>{j.status}</Badge></td><td className="tabular-nums">{j.progress?.unique_companies ?? "–"}</td>
              <td className="tabular-nums">${j.spent_usd.toFixed(3)} / ${j.budget_usd}</td><td className="muted">{new Date(j.created_at).toLocaleString()}</td></tr>))}
          </tbody></table>
        {jobs && !jobs.length && <div className="p-4 text-sm muted">No research yet.</div>}
      </div>
    </div>
  );
}
