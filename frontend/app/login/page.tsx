"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setToken } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", organization_name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const r = await api<{ access_token: string }>(`/api/auth/${mode}`, { method: "POST", json: body });
      setToken(r.access_token);
      router.replace("/");
    } catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-3">
        <h1 className="text-lg font-semibold">Global Buyer Intel</h1>
        <p className="text-sm muted">{mode === "login" ? "Sign in to your workspace" : "Create an organisation workspace"}</p>
        <ErrorBox error={error} />
        {mode === "register" && (
          <div><label className="label" htmlFor="org">Organisation</label>
            <input id="org" className="input" required value={form.organization_name} onChange={(e) => setForm({ ...form, organization_name: e.target.value })} /></div>
        )}
        <div><label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" className="input" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div><label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" minLength={8} className="input" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
        <button className="btn w-full justify-center" disabled={busy}>{mode === "login" ? "Sign in" : "Create workspace"}</button>
        <button type="button" className="w-full text-center text-sm underline" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New here? Create a workspace" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
