"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, BUYER_LABELS } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

type Options = { countries: { code: string; name: string; name_tr: string; region: string; languages: string[]; cities: string[] }[];
  product_categories: { code: string; label: string }[]; buyer_types: string[] };

const REGIONS: Record<string, string> = { europe: "Europe", middle_east: "Middle East", north_africa: "North Africa", caucasus: "Caucasus" };
const DEFAULT_TYPES = ["wholesaler", "distributor", "verified_importer", "retail_chain", "independent_store", "contract_ffe"];

export default function NewResearch() {
  const router = useRouter();
  const [opts, setOpts] = useState<Options | null>(null);
  const [sources, setSources] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [countries, setCountries] = useState<string[]>([]);
  const [products, setProducts] = useState<string[]>(["dining_table", "chair"]);
  const [types, setTypes] = useState<string[]>(DEFAULT_TYPES);
  const [product, setProduct] = useState({ price_segment: "", materials: "", supply_models: [] as string[], moq: "", capacity: "", design_segment: "" });
  const [target, setTarget] = useState(200);
  const [minFit, setMinFit] = useState(50);
  const [budget, setBudget] = useState(10);
  const [paid, setPaid] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [catalog, setCatalog] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Options>("/api/research/options").then(setOpts).catch((e) => setError(e.message));
    api<any[]>("/api/sources").then((s) => setSources(s.filter((x) => x.purposes.includes("discovery")))).catch(() => {});
  }, []);

  const byRegion = useMemo(() => {
    const m: Record<string, Options["countries"]> = {};
    opts?.countries.forEach((c) => { (m[c.region] ??= []).push(c); });
    return m;
  }, [opts]);

  async function parseText() {
    setError(null);
    try {
      const p = await api("/api/research/parse", { method: "POST", json: { text } });
      if (p.countries.length) setCountries(p.countries);
      if (p.product_categories.length) setProducts(p.product_categories);
      if (p.buyer_types.length) setTypes(p.buyer_types);
    } catch (e: any) { setError(e.message); }
  }

  async function uploadCatalog(f: File) {
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api("/api/research/catalog/analyze", { method: "POST", body: fd });
      setCatalog(r);
      if (r.categories.length) setProducts(r.categories);
      if (r.materials.length) setProduct((p) => ({ ...p, materials: r.materials.join(", ") }));
    } catch (e: any) { setError(e.message); }
  }

  function toggle(list: string[], v: string, set: (x: string[]) => void) { set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]); }

  async function submit() {
    setBusy(true); setError(null);
    try {
      const job = await api("/api/research/jobs", { method: "POST", json: {
        request_text: text || null, countries, buyer_types: types, target_company_count: target, min_buyer_fit: minFit, budget_usd: budget,
        use_paid_sources: paid, selected_sources: selected,
        product: { categories: products, price_segment: product.price_segment || null,
                   materials: product.materials.split(",").map((s) => s.trim()).filter(Boolean), supply_models: product.supply_models,
                   moq: product.moq || null, capacity: product.capacity || null,
                   design_segment: product.design_segment.split(",").map((s) => s.trim()).filter(Boolean),
                   hs_codes: catalog?.hs_codes?.map((h: any) => h.code) ?? [], catalog_analysis: catalog },
      } });
      router.push(`/research/${job.id}`);
    } catch (e: any) { setError(e.message); setBusy(false); }
  }

  if (!opts) return <div className="muted">Loading…</div>;
  return (
    <div className="max-w-5xl space-y-4">
      <h1 className="text-xl font-semibold">New research</h1>
      <ErrorBox error={error} />
      <section className="card space-y-2">
        <label className="label" htmlFor="req">Describe what you are looking for (Turkish or English)</label>
        <textarea id="req" className="input min-h-[80px]" value={text} onChange={(e) => setText(e.target.value)}
                  placeholder="Almanya, Fransa, Irak, Fas ve Gürcistan'da yemek masası ve sandalye ithal eden, toptan satan veya perakende zinciri işleten potansiyel müşterileri bul." />
        <button className="btn-ghost" onClick={parseText} disabled={!text.trim()}>Parse into parameters</button>
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">Product</h2>
        <div className="flex flex-wrap items-center gap-2">
          <label className="btn-ghost cursor-pointer">Upload catalogue (PDF/CSV/XLSX)
            <input type="file" className="hidden" accept=".pdf,.csv,.xlsx,.txt" onChange={(e) => e.target.files?.[0] && uploadCatalog(e.target.files[0])} /></label>
          {catalog && <span className="text-sm muted">Detected: {catalog.categories.join(", ") || "nothing"}; materials: {catalog.materials.join(", ") || "–"}</span>}
        </div>
        {catalog?.hs_codes?.length > 0 && (
          <div className="text-sm"><span className="label">Suggested HS codes</span>
            <ul className="list-inside list-disc">{catalog.hs_codes.map((h: any, i: number) => (
              <li key={i}><b>{h.code}</b> {h.description} <span className="muted">({h.category}, confidence {Math.round(h.confidence * 100)}% – {h.reasoning})</span></li>))}</ul>
            <p className="text-xs muted">{catalog.notes}</p></div>
        )}
        <div className="flex flex-wrap gap-2">{opts.product_categories.map((p) => (
          <label key={p.code} className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${products.includes(p.code) ? "border-brand bg-brand text-white" : "border-slate-300 dark:border-slate-700"}`}>
            <input type="checkbox" className="sr-only" checked={products.includes(p.code)} onChange={() => toggle(products, p.code, setProducts)} />{p.label}</label>))}
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div><label className="label" htmlFor="seg">Price segment</label>
            <select id="seg" className="input" value={product.price_segment} onChange={(e) => setProduct({ ...product, price_segment: e.target.value })}>
              <option value="">any</option><option value="economy">economy</option><option value="mid">mid</option><option value="upper">upper</option><option value="luxury">luxury</option></select></div>
          <div><label className="label" htmlFor="mat">Materials</label>
            <input id="mat" className="input" value={product.materials} onChange={(e) => setProduct({ ...product, materials: e.target.value })} placeholder="wood, metal, upholstered" /></div>
          <div><label className="label" htmlFor="des">Design segment</label>
            <input id="des" className="input" value={product.design_segment} onChange={(e) => setProduct({ ...product, design_segment: e.target.value })} placeholder="modern, contract" /></div>
          <div><label className="label" htmlFor="moq">MOQ</label><input id="moq" className="input" value={product.moq} onChange={(e) => setProduct({ ...product, moq: e.target.value })} /></div>
          <div><label className="label" htmlFor="cap">Capacity</label><input id="cap" className="input" value={product.capacity} onChange={(e) => setProduct({ ...product, capacity: e.target.value })} /></div>
          <div><span className="label">Supply model</span><div className="flex flex-wrap gap-2 text-sm">{["oem", "odm", "private_label", "own_brand", "project"].map((m) => (
            <label key={m} className="flex items-center gap-1"><input type="checkbox" checked={product.supply_models.includes(m)}
              onChange={() => setProduct({ ...product, supply_models: product.supply_models.includes(m) ? product.supply_models.filter((x) => x !== m) : [...product.supply_models, m] })} />{m}</label>))}</div></div>
        </div>
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">Target markets <span className="text-sm font-normal muted">({countries.length} selected)</span></h2>
        {Object.entries(byRegion).map(([region, list]) => (
          <div key={region}><div className="label">{REGIONS[region] ?? region}</div>
            <div className="flex flex-wrap gap-2">{list.map((c) => (
              <label key={c.code} title={`Languages: ${c.languages.join(", ")} · Cities: ${c.cities.slice(0, 6).join(", ")}…`}
                     className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${countries.includes(c.code) ? "border-brand bg-brand text-white" : "border-slate-300 dark:border-slate-700"}`}>
                <input type="checkbox" className="sr-only" checked={countries.includes(c.code)} onChange={() => toggle(countries, c.code, setCountries)} />{c.name}</label>))}</div></div>
        ))}
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">Buyer types</h2>
        <div className="flex flex-wrap gap-2">{opts.buyer_types.filter((t) => t !== "unclear").map((t) => (
          <label key={t} className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${types.includes(t) ? "border-brand bg-brand text-white" : "border-slate-300 dark:border-slate-700"}`}>
            <input type="checkbox" className="sr-only" checked={types.includes(t)} onChange={() => toggle(types, t, setTypes)} />{BUYER_LABELS[t] ?? t}</label>))}</div>
        <p className="text-xs muted">“Verified importer” is only assigned with shipment-grade evidence (licensed P2 data); otherwise import activity is shown as “claimed”.</p>
      </section>

      <section className="card grid gap-3 sm:grid-cols-4">
        <div><label className="label" htmlFor="target">Companies wanted</label><input id="target" type="number" min={1} className="input" value={target} onChange={(e) => setTarget(+e.target.value)} /></div>
        <div><label className="label" htmlFor="minfit">Min. buyer fit</label><input id="minfit" type="number" min={0} max={100} className="input" value={minFit} onChange={(e) => setMinFit(+e.target.value)} /></div>
        <div><label className="label" htmlFor="budget">Budget (USD)</label><input id="budget" type="number" min={0} step="0.5" className="input" value={budget} onChange={(e) => setBudget(+e.target.value)} /></div>
        <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={paid} onChange={(e) => setPaid(e.target.checked)} /> Use paid data providers</label>
      </section>

      <section className="card space-y-2">
        <h2 className="font-semibold">Discovery sources <span className="text-sm font-normal muted">(none selected = all permitted)</span></h2>
        <div className="grid gap-1 sm:grid-cols-2">{sources.map((s) => (
          <label key={s.key} className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={selected.includes(s.key)} onChange={() => toggle(selected, s.key, setSelected)} />
            <span><b>{s.name}</b> <span className="muted">{s.tier}</span> {s.usable ? <span className="text-emerald-700 dark:text-emerald-300">● ready</span>
              : <span className="muted">○ {s.blocked_reason}</span>}</span></label>))}</div>
      </section>

      <button className="btn" disabled={busy || !countries.length} onClick={submit}>{busy ? "Starting…" : "Start research"}</button>
    </div>
  );
}
