"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Deck, { toolSubject, type DeckSubject } from "@/components/Deck";
import FolderFan, { type FanItem } from "@/components/FolderFan";
import Icon from "@/components/Icon";
import { api, type Library, type LibraryEntry, type Run } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";
import { formats } from "@/lib/formats";
import { allEntries, kindLabel, matches, openHref, successRate } from "@/lib/library";

type Mode = "workflows" | "tools";

export default function Dashboard() {
  const { meta, stats, toast, refreshStats, op } = useApp();
  const router = useRouter();
  const [mode, setMode] = useState<Mode | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [library, setLibrary] = useState<Library | null>(null);

  useEffect(() => {
    refreshStats();
    api<Run[]>("GET", "/api/history?limit=6").then(setRuns).catch(() => {});
    api<Library>("GET", "/api/library").then((lib) => {
      setLibrary(lib);
      setMode((m) => m ?? (allEntries(lib).length ? "workflows" : "tools"));   // workflows first once there are some
    }).catch(() => setMode((m) => m ?? "tools"));
  }, [refreshStats]);

  const workflows = useMemo(() => allEntries(library).filter((e) => matches(e, query, op)), [library, query, op]);
  const tools = useMemo(() => (meta?.operations ?? []).filter((o) =>
    (filter === "all" || o.category === filter) && `${o.name} ${o.description}`.toLowerCase().includes(query.trim().toLowerCase())),
  [meta, filter, query]);

  const items: FanItem[] = mode === "workflows"
    ? workflows.map((e) => ({
        id: e.key, title: e.name, icon: op(e.steps[0])?.category ?? "workflow",
        caption: `${kindLabel(e)} · ${e.steps.length} step${e.steps.length === 1 ? "" : "s"}`, stat: successRate(e),
      }))
    : tools.map((o) => {
        const stat = stats?.targets[o.id];
        return {
          id: o.id, title: o.name, icon: o.category,
          caption: `${meta?.categories[o.category]} · ${stat ? stat.runs : 0} run${stat?.runs === 1 ? "" : "s"}`,
          stat: stat ? `${Math.round((100 * stat.ok) / stat.runs)}%` : "New",
        };
      });
  const current = items.find((i) => i.id === selected) ?? items[Math.min(Math.floor(items.length / 2), items.length - 1)];

  const entryOf = (id: string): LibraryEntry | undefined => workflows.find((e) => e.key === id);
  const subject: DeckSubject | undefined = (() => {
    if (!current) return undefined;
    if (mode === "tools") {
      const tool = op(current.id);
      return tool ? toolSubject(tool, stats?.targets[tool.id]) : undefined;
    }
    const entry = entryOf(current.id);
    if (!entry) return undefined;
    const first = op(entry.steps[0]);
    const last = op(entry.steps[entry.steps.length - 1]);
    return {
      key: entry.key, title: entry.name, icon: "workflow",
      reads: first ? formats(first.input_extensions) : "Files", writes: last ? formats(last.output_extensions) : "Files",
      detail: entry.steps.map((id) => op(id)?.name ?? id).join(" → "),
      summary: entry.last_summary || `${kindLabel(entry)} — open it, choose the input files and run it.`,
      runs: entry.runs, ok: entry.ok, lastRun: entry.last_run, lastStatus: entry.last_status, openLabel: "Open workflow",
    };
  })();
  const open = (id: string) => {
    if (mode === "tools") return router.push(`/tool/?id=${id}`);
    const entry = entryOf(id);
    if (entry) router.push(openHref(entry));
  };

  const exportHistory = async () => {
    try {
      const { path } = await api<{ path: string }>("POST", "/api/history/export");
      toast(`History exported to ${path}`);
      openPath(path).catch(() => {});
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  if (!meta || !mode) return null;
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="toolbar-row">
        <div className="segmented">
          {(["workflows", "tools"] as Mode[]).map((m) => (
            <button key={m} className={mode === m ? "on" : ""} onClick={() => { setMode(m); setSelected(""); }}>
              <Icon name={m === "workflows" ? "folder" : "excel"} size={17} />
              {m === "workflows" ? `Workflows (${allEntries(library).length})` : `Tools (${meta.operations.length})`}
              {mode === m && <motion.span layoutId="dash-mode" className="seg-bg" />}
            </button>
          ))}
        </div>
        <div className="lib-search" style={{ width: 280 }}>
          <Icon name="search" size={17} />
          <input className="input" style={{ borderRadius: 20, height: 40 }} value={query} onChange={(e) => { setQuery(e.target.value); setSelected(""); }}
            placeholder={mode === "workflows" ? "Search workflows by name, folder or tool…" : "Search tools…"} />
        </div>
        {mode === "tools" && (
          <label className="chip" style={{ position: "relative" }}>
            <Icon name="folder" size={18} />
            <select value={filter} onChange={(e) => setFilter(e.target.value)} className="chip-select">
              <option value="all">All tools</option>
              {Object.entries(meta.categories).filter(([k]) => k !== "cross").map(([k, v]) => <option key={k} value={k}>{v} only</option>)}
            </select>
            <Icon name="down" size={16} />
          </label>
        )}
        <div className="grow" />
        <button className="chip" onClick={() => router.push("/workflows/")}><Icon name="folder" size={18} />All workflows</button>
        <button className="chip" onClick={exportHistory}><Icon name="export" size={18} />Export</button>
        <button className="chip" onClick={() => router.push("/workflow/")}><Icon name="plus" size={18} />New workflow</button>
      </div>
      {items.length ? (
        <FolderFan key={mode} items={items} selected={current?.id ?? ""} onSelect={setSelected} onOpen={open} />
      ) : (
        <div className="fan empty-fan">
          <div className="lib-empty">
            <Icon name="folder" size={36} />
            <div>{query ? `Nothing matches “${query}”.` : "No workflow yet. Build one, or describe it to the AI assistant — it will appear here as a folder."}</div>
            <div className="row">
              <button className="btn primary" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />Build a workflow</button>
              <button className="btn pink" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={16} />Ask AI</button>
            </div>
          </div>
        </div>
      )}
      <Deck subject={subject} runs={runs} workflows={(library?.saved ?? []).map((e) => ({ name: e.name, steps: e.steps }))}
        onOpen={() => current && open(current.id)}
        onOpenRun={(run) => run.kind === "operation" ? router.push(`/tool/?id=${run.target_id}`) : router.push(`/workflow/?name=${encodeURIComponent(run.target_id)}`)}
        onOpenWorkflow={(name) => router.push(name ? `/workflow/?name=${encodeURIComponent(name)}` : "/workflow/")}
        onNewRun={() => router.push(mode === "tools" && current ? `/tool/?id=${current.id}` : "/workflow/")} />
    </div>
  );
}
