"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import ErrorBoundary from "./ErrorBoundary";
import Icon from "./Icon";
import { useApp } from "@/lib/app-context";
import { bridge, whenBridgeReady } from "@/lib/desktop";

const NAV = [
  { href: "/", label: "Dashboard", icon: "home" },
  { href: "/toolbox/?cat=excel", label: "Excel Toolbox", icon: "excel", match: "excel" },
  { href: "/toolbox/?cat=pdf", label: "PDF Toolbox", icon: "pdf", match: "pdf" },
  { href: "/toolbox/?cat=word", label: "Word Toolbox", icon: "word", match: "word" },
  { href: "/workflow/", label: "Workflow Builder", icon: "workflow" },
  { href: "/assistant/", label: "AI Assistant", icon: "sparkle" },
];
const NAV_BOTTOM = [
  { href: "/history/", label: "History", icon: "history" },
  { href: "/logs/", label: "Logs", icon: "logs" },
  { href: "/settings/", label: "Settings", icon: "settings" },
];

function useCategory(): string {
  const [category, setCategory] = useState("");
  const pathname = usePathname();
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (pathname.startsWith("/toolbox")) setCategory(params.get("cat") ?? "");
    else if (pathname.startsWith("/tool")) setCategory((params.get("id") ?? "").split(".")[0]);
    else setCategory("");
  }, [pathname]);
  return category;
}

function Rail() {
  const pathname = usePathname();
  const category = useCategory();
  const { railCollapsed } = useApp();
  const isActive = (item: { href: string; match?: string }) => {
    if (item.match) return category === item.match;
    if (item.href === "/") return pathname === "/";
    return pathname.startsWith(item.href.replace(/\/$/, ""));
  };
  const render = (item: (typeof NAV)[number]) => (
    <Link key={item.href} href={item.href} className={`nav ${isActive(item) ? "active" : ""}`} title={item.label}>
      {isActive(item) && <motion.span layoutId="nav-bg" className="bg" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
      <Icon name={item.icon} />
      {!railCollapsed && <span>{item.label}</span>}
    </Link>
  );
  return (
    <nav className={`rail ${railCollapsed ? "collapsed" : ""}`} style={{ isolation: "isolate" }}>
      {NAV.map(render)}
      <div className="gap" />
      {NAV_BOTTOM.map(render)}
    </nav>
  );
}

function Search() {
  const { meta } = useApp();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState(false);
  const [active, setActive] = useState(0);
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !meta) return [];
    return meta.operations.filter((o) => `${o.name} ${o.description}`.toLowerCase().includes(q)).slice(0, 7);
  }, [query, meta]);
  const open = (id: string) => {
    router.push(`/tool/?id=${id}`);
    setQuery("");
  };
  return (
    <div className="search">
      <Icon name="search" size={18} />
      <input placeholder="Search tools…" value={query} onChange={(e) => { setQuery(e.target.value); setActive(0); }}
        onFocus={() => setFocus(true)} onBlur={() => setTimeout(() => setFocus(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, results.length - 1));
          if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          if (e.key === "Enter" && results[active]) open(results[active].id);
          if (e.key === "Escape") setQuery("");
        }} />
      {focus && results.length > 0 && (
        <div className="results">
          {results.map((op, i) => (
            <button key={op.id} className={i === active ? "active" : ""} onMouseDown={() => open(op.id)}>
              <Icon name={op.category} size={18} />
              <span className="grow ellipsis">{op.name}</span>
              <span className="faint" style={{ fontSize: 12 }}>{meta?.categories[op.category]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusPill() {
  const { activeJobs, stats, meta } = useApp();
  const router = useRouter();
  const job = activeJobs[activeJobs.length - 1];
  const [now, setNow] = useState("");
  useEffect(() => {
    const tick = () => setNow(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    tick();
    const id = setInterval(tick, 20_000);
    return () => clearInterval(id);
  }, []);
  let text = meta ? `Ready · ${meta.operations.length} tools · works offline` : "Starting…";
  let fill = 0;
  if (job) {
    const p = job.state?.progress;
    fill = p && p.total ? (100 * p.done) / p.total : 0;
    text = `${job.label} · ${p?.message || "Working…"}`;
  } else if (stats && stats.runs) {
    const last = Object.values(stats.targets).sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
    if (last) text = `Last task · ${last.summary}`;
  }
  return (
    <div className="statuspill" onClick={() => router.push("/history/")} title={text}>
      <motion.div className="fill" animate={{ width: `${fill}%` }} />
      <span className="dot">{job ? <span className="spin" /> : <Icon name="check" size={16} />}</span>
      <span className="text">{text}</span>
      <span className="time">{now}</span>
    </div>
  );
}

function WindowControls() {
  const [desktop, setDesktop] = useState(false);
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    whenBridgeReady().then(async (b) => {
      setDesktop(!!b);
      if (b) setMaximized(await b.is_maximized());
    });
  }, []);
  if (!desktop) return null;
  return (
    <div className="row" style={{ gap: 4, marginLeft: 6 }}>
      <button className="winctl" title="Minimise" onClick={() => bridge()?.minimize()}><Icon name="winmin" size={16} /></button>
      <button className="winctl" title={maximized ? "Restore" : "Maximise"}
        onClick={async () => setMaximized((await bridge()?.toggle_maximize()) ?? false)}>
        <Icon name={maximized ? "winrestore" : "winmax"} size={15} />
      </button>
      <button className="winctl close" title="Close" onClick={() => bridge()?.close()}><Icon name="x" size={16} /></button>
    </div>
  );
}

function ResizeHandles() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    whenBridgeReady().then((b) => setEnabled(!!b));
  }, []);
  const start = async (edge: string, event: React.PointerEvent) => {
    const native = bridge();
    if (!native || (await native.is_maximized())) return;
    const target = event.currentTarget as HTMLElement;
    target.setPointerCapture(event.pointerId);
    const origin = { x: event.screenX, y: event.screenY };
    const g = await native.geometry();
    let frame = 0;
    const move = (e: PointerEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const dx = e.screenX - origin.x;
        const dy = e.screenY - origin.y;
        let { x, y, width, height } = g;
        if (edge.includes("e")) width = g.width + dx;
        if (edge.includes("s")) height = g.height + dy;
        if (edge.includes("w")) { width = g.width - dx; x = g.x + dx; }
        if (edge.includes("n")) { height = g.height - dy; y = g.y + dy; }
        native.set_geometry(x, y, width, height);
      });
    };
    const end = () => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", end);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", end);
  };
  if (!enabled) return null;
  return (
    <>
      {["n", "s", "e", "w", "ne", "nw", "se", "sw"].map((edge) => (
        <div key={edge} className={`edge ${edge}`} onPointerDown={(e) => start(edge, e)} />
      ))}
    </>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const { error, settings, saveSettings, stats, railCollapsed, setRailCollapsed, meta } = useApp();
  const uiVersion = process.env.NEXT_PUBLIC_UI_VERSION ?? "";
  const mismatch = meta && uiVersion && meta.version !== uiVersion;
  const router = useRouter();
  const pathname = usePathname();
  const failed = stats ? stats.runs - stats.ok : 0;
  const today = new Date().toLocaleDateString([], { month: "long", day: "numeric" });
  const titlebar = useRef<HTMLDivElement>(null);

  const toggleMaximize = (event: React.MouseEvent) => {
    const target = event.target as HTMLElement;
    if (target.classList.contains("drag-region")) bridge()?.toggle_maximize();
  };

  return (
    <div className="app">
      <ResizeHandles />
      <header className="titlebar drag-region" ref={titlebar} onDoubleClick={toggleMaximize}>
        <Link href="/" className="round logo" title="OfficeFlow"><Logo /></Link>
        <button className="round" title="Show or hide menu labels" onClick={() => setRailCollapsed(!railCollapsed)}>
          <Icon name="menu" size={19} />
        </button>
        <Search />
        <div className="spacer drag-region" />
        <div className="pill"><Icon name="calendar" size={18} />{today}</div>
        <StatusPill />
        <div className="spacer drag-region" />
        <button className="round" title="Settings" onClick={() => router.push("/settings/")}><Icon name="settings" size={19} /></button>
        <button className="round" title="Tasks with problems — open the history" onClick={() => router.push("/history/")}>
          <Icon name="bell" size={19} />
          {failed > 0 && <span className="badge">{Math.min(failed, 99)}</span>}
        </button>
        <button className="round" title="Switch theme"
          onClick={() => saveSettings({ theme: settings?.theme === "light" ? "dark" : "light" })}>
          <Icon name={settings?.theme === "light" ? "moon" : "sun"} size={19} />
        </button>
        <WindowControls />
      </header>
      <Rail />
      <main className="main">
        {error ? (
          <div className="page"><div className="banner failed"><b>Cannot reach OfficeFlow’s engine.</b><div className="muted">{error}</div></div></div>
        ) : (
          <AnimatePresence mode="wait">
            <motion.div key={pathname} className="page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
              {mismatch && (
                <div className="banner warning" style={{ marginBottom: 14 }}>
                  <b>OfficeFlow was only partly updated.</b> The interface is version {uiVersion} but the engine is {meta?.version}.
                  Close every OfficeFlow window, then start it again with <code>python -m officeflow</code>.
                </div>
              )}
              <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>
            </motion.div>
          </AnimatePresence>
        )}
      </main>
    </div>
  );
}

function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
      <path d="M17.5 7.5A7 7 0 1 0 19 13" />
      <path d="M13 13l6 6" />
    </svg>
  );
}
