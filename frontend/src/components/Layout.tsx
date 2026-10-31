import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../lib/api";
import AccessGate from "./AccessGate";

const link = ({ isActive }: { isActive: boolean }) =>
  `block rounded px-3 py-1.5 text-[0.95rem] ${isActive ? "bg-marker font-medium" : "text-muted hover:text-ink"}`;

function Provider({ name, ready, hint }: { name: string; ready: boolean; hint: string }) {
  return (
    <li className="flex items-center gap-2" title={ready ? "Key found" : hint}>
      <span className={`h-2 w-2 rounded-full ${ready ? "bg-ok" : "bg-warn"}`} aria-hidden />
      <span>{name}</span>
      <span className="text-muted">{ready ? "ready" : "no key"}</span>
    </li>
  );
}

export default function Layout() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 });
  const p = health.data?.providers;
  const locked = !!health.data?.auth.required && !health.data.auth.ok;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[14rem_1fr]">
      <aside className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-rule px-5 py-4 md:flex-col md:items-stretch md:border-b-0 md:border-r md:py-8">
        <div className="font-serif text-xl font-semibold tracking-tight">Blog Studio</div>
        <nav className="flex gap-1 md:flex-col" aria-label="Main">
          <NavLink to="/" end className={link}>Write</NavLink>
          <NavLink to="/library" className={link}>Library</NavLink>
        </nav>
        <div className="ml-auto text-sm md:ml-0 md:mt-auto">
          {health.isError ? (
            <p className="text-bad">Backend not reachable. Start it on port 8000.</p>
          ) : p ? (
            <ul className="m-0 list-none space-y-1 p-0">
              <Provider name="Groq" ready={p.groq} hint="Set GROQ_API_KEY in backend/.env" />
              <Provider name="Tavily" ready={p.tavily} hint="Set TAVILY_API_KEY in backend/.env (research is skipped without it)" />
              <Provider name="Cloudflare" ready={p.cloudflare_images} hint="Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN (images are skipped without them)" />
            </ul>
          ) : null}
        </div>
      </aside>
      <main className="min-w-0 px-5 py-8 md:px-10">
        {locked ? <AccessGate /> : <Outlet />}
      </main>
    </div>
  );
}
