"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/research/new", label: "New Research" },
  { href: "/research", label: "Research Monitor" },
  { href: "/companies", label: "Companies" },
  { href: "/reviews", label: "Duplicate Review" },
  { href: "/sources", label: "Source Manager" },
  { href: "/exports", label: "Exports" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<{ email: string; role: string } | null>(null);
  const [open, setOpen] = useState(false);
  const isLogin = path === "/login";

  useEffect(() => {
    if (isLogin) return;
    if (!getToken()) { router.replace("/login"); return; }
    api("/api/auth/me").then(setMe).catch(() => router.replace("/login"));
  }, [isLogin, router]);

  if (isLogin) return <>{children}</>;
  if (!me) return <div className="p-8 muted">Loading…</div>;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[220px_1fr]">
      <aside className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 md:min-h-screen md:border-b-0 md:border-r">
        <div className="flex items-center justify-between p-4">
          <div>
            <div className="text-sm font-bold text-brand dark:text-blue-300">Global Buyer Intel</div>
            <div className="text-xs muted">Furniture export leads</div>
          </div>
          <button className="btn-ghost md:hidden" onClick={() => setOpen(!open)} aria-label="Toggle menu">☰</button>
        </div>
        <nav className={`${open ? "block" : "hidden"} md:block`}>
          {NAV.map((n) => {
            const active = n.href === "/" ? path === "/" : path === n.href || (n.href !== "/research" && path.startsWith(n.href + "/")) ||
              (n.href === "/research" && path.startsWith("/research/") && !path.startsWith("/research/new"));
            return (
              <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
                    className={`block px-4 py-2 text-sm ${active ? "bg-slate-100 font-semibold dark:bg-slate-800" : "hover:bg-slate-50 dark:hover:bg-slate-800/60"}`}>
                {n.label}
              </Link>
            );
          })}
          <div className="mt-4 border-t border-slate-200 p-4 text-xs dark:border-slate-800">
            <div className="truncate">{me.email}</div>
            <div className="muted">{me.role}</div>
            <button className="mt-2 underline" onClick={() => { setToken(null); router.replace("/login"); }}>Sign out</button>
          </div>
        </nav>
      </aside>
      <main className="min-w-0 p-4 md:p-6">{children}</main>
    </div>
  );
}
