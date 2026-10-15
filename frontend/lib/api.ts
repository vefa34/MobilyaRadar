export const TOKEN_KEY = "gb_token";

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  const res = await fetch(path, { ...opts, headers, body });
  if (res.status === 401 && typeof window !== "undefined" && !path.includes("/auth/")) {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res as unknown)) as T;
}

export async function download(path: string, fallbackName: string) {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] || fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
  return { rows: res.headers.get("x-export-rows"), withheld: res.headers.get("x-export-withheld-fields"),
           excluded: res.headers.get("x-export-excluded-companies") };
}

export const BUYER_LABELS: Record<string, string> = {
  verified_importer: "Verified importer", wholesaler: "Wholesaler", distributor: "Distributor", retail_chain: "Retail chain",
  independent_store: "Independent store", ecommerce: "E-commerce", contract_ffe: "Contract / FF&E", brand_private_label: "Brand / private label",
  interior_procurement: "Interior procurement", tender_buyer: "Tender buyer", manufacturer: "Manufacturer", unclear: "Unclear",
};

export const PRIORITY_LABELS: Record<string, string> = {
  high_priority: "High priority", promising_needs_verification: "Promising – verify", real_but_not_target: "Not target",
  medium: "Medium", low: "Low",
};
