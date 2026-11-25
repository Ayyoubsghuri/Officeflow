"use client";

// Home: the workflow library as folders. Folders open in place; a workflow folder
// is selected with one click (its details show in the deck below) and opened with
// a double click, Enter, or the Open button.

import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Deck, { type DeckSubject } from "@/components/Deck";
import FolderGlyph from "@/components/FolderGlyph";
import Icon from "@/components/Icon";
import { api, type Library, type LibraryEntry, type Run } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";
import { formats } from "@/lib/formats";
import {
  AI, RAN, allEntries, childFolders, flowFormats, folderTree, inFolder, kindLabel, matches, openHref, successRate, underFolder,
} from "@/lib/library";

type Tile =
  | { type: "folder"; key: string; folder: string; name: string; count: number; tone: "grey" | "blue" }
  | { type: "flow"; key: string; entry: LibraryEntry };

function tone(entry: LibraryEntry): "grey" | "green" | "amber" | "blue" {
  if (entry.kind === "ai") return "blue";
  if (entry.last_status === "failed") return "amber";
  return entry.runs ? "green" : "grey";
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

export default function Home() {
  const { meta, toast, refreshStats, op } = useApp();
  const router = useRouter();
  const [library, setLibrary] = useState<Library | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [folder, setFolder] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");

  useEffect(() => {
    refreshStats();
    api<Run[]>("GET", "/api/history?limit=6").then(setRuns).catch(() => {});
    api<Library>("GET", "/api/library").then(setLibrary).catch((e) => toast(String(e), "error"));
  }, [refreshStats, toast]);

  const entries = useMemo(() => allEntries(library), [library]);
  const searching = query.trim().length > 0;

  const tiles: Tile[] = useMemo(() => {
    if (!library) return [];
    if (searching) return entries.filter((e) => matches(e, query, op)).map((entry) => ({ type: "flow", key: entry.key, entry }));
    const out: Tile[] = [];
    if (folder !== RAN && folder !== AI) {
      for (const f of childFolders(folderTree(library.folders), folder)) {
        out.push({ type: "folder", key: `dir:${f}`, folder: f, name: f.split("/").pop()!, tone: "grey",
          count: entries.filter((e) => underFolder(e, f)).length });
      }
    }
    if (!folder) {
      if (library.ai.length) out.push({ type: "folder", key: "dir:ai", folder: AI, name: "AI proposals", count: library.ai.length, tone: "blue" });
      if (library.recent.length) out.push({ type: "folder", key: "dir:ran", folder: RAN, name: "Ran, not saved", count: library.recent.length, tone: "grey" });
      for (const entry of library.saved.filter((e) => !e.folder)) out.push({ type: "flow", key: entry.key, entry });
    } else {
      for (const entry of entries.filter((e) => inFolder(e, folder))) out.push({ type: "flow", key: entry.key, entry });
    }
    return out;
  }, [library, entries, folder, query, searching, op]);

  const flows = tiles.flatMap((t) => (t.type === "flow" ? [t.entry] : []));
  const current = flows.find((e) => e.key === selected) ?? flows[0];

  const subject: DeckSubject | undefined = (() => {
    if (!current) return undefined;
    const first = op(current.steps[0]);
    const last = op(current.steps[current.steps.length - 1]);
    return {
      key: current.key, title: current.name, icon: "workflow",
      reads: first ? formats(first.input_extensions) : "Files", writes: last ? formats(last.output_extensions) : "Files",
      detail: current.steps.map((id) => op(id)?.name ?? id).join(" → "),
      summary: current.last_summary || `${kindLabel(current)} — open it, choose the input files and run it.`,
      runs: current.runs, ok: current.ok, lastRun: current.last_run, lastStatus: current.last_status, openLabel: "Open workflow",
    };
  })();

  const open = (entry: LibraryEntry) => router.push(openHref(entry));
  const enter = (f: string) => { setFolder(f); setSelected(""); setQuery(""); };

  const exportHistory = async () => {
    try {
      const { path } = await api<{ path: string }>("POST", "/api/history/export");
      toast(`History exported to ${path}`);
      openPath(path).catch(() => {});
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  const crumbs = folder === RAN ? ["Ran, not saved"] : folder === AI ? ["AI proposals"] : folder ? folder.split("/") : [];
  const title = searching ? `Results for “${query}”` : crumbs.length ? crumbs[crumbs.length - 1] : "Your workflows";

  if (!meta || !library) return null;
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="home-head">
        <div className="home-crumbs">
          <button className={!folder && !searching ? "on" : ""} onClick={() => enter("")}><Icon name="home" size={16} />Workflows</button>
          {!searching && crumbs.map((c, i) => (
            <span key={i} className="row" style={{ gap: 6 }}>
              <Icon name="forward" size={14} />
              <button className={i === crumbs.length - 1 ? "on" : ""}
                onClick={() => folder !== RAN && folder !== AI && enter(crumbs.slice(0, i + 1).join("/"))}>{c}</button>
            </span>
          ))}
        </div>
        <div className="grow" />
        <div className="lib-search" style={{ width: 280 }}>
          <Icon name="search" size={17} />
          <input className="input" style={{ borderRadius: 20, height: 38 }} value={query}
            onChange={(e) => { setQuery(e.target.value); setSelected(""); }} placeholder="Search workflows by name, folder or tool…" />
        </div>
        <button className="btn icon ghost" title="Manage folders" onClick={() => router.push(folder && folder !== RAN && folder !== AI ? `/workflows/?folder=${encodeURIComponent(folder)}` : "/workflows/")}>
          <Icon name="folder" size={18} />
        </button>
        <button className="btn icon ghost" title="Export history" onClick={exportHistory}><Icon name="export" size={18} /></button>
        <button className="btn icon ghost" title="Ask the AI to build a workflow" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={17} /></button>
        <button className="btn icon ghost" title="New workflow" onClick={() => router.push("/workflow/")}><Icon name="plus" size={18} /></button>
      </div>

      <div className="home-title">
        <h1 className="h1">{title}</h1>
        <span className="muted">{searching ? plural(tiles.length, "workflow") : folder === RAN || folder === AI ? plural(flows.length, "workflow")
          : folder ? plural(entries.filter((e) => underFolder(e, folder)).length, "workflow") : `${plural(entries.length, "workflow")} in total`}</span>
      </div>

      <div className="home-folders">
        {tiles.length === 0 ? (
          <div className="lib-empty" style={{ gridColumn: "1 / -1" }}>
            <FolderGlyph size="lg" label="OfficeFlow" />
            <div>{searching ? `Nothing matches “${query}”.` : entries.length ? "This folder is empty."
              : "No workflow yet. Build one, or describe it to the AI assistant — it will appear here as a folder."}</div>
            <div className="row">
              <button className="btn primary" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />Build a workflow</button>
              <button className="btn pink" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={16} />Ask AI</button>
            </div>
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {tiles.map((t, i) => {
              const isFlow = t.type === "flow";
              const on = isFlow && current?.key === t.key;
              return (
                <motion.div key={`${folder}|${t.key}`} className={`home-tile ${isFlow ? "flow" : "dir"} ${on ? "on" : ""}`}
                  role="button" tabIndex={0} title={isFlow ? t.entry.last_summary || t.entry.name : `Open the folder ${t.name}`}
                  initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                  transition={{ delay: Math.min(i, 14) * 0.025 }}
                  onClick={() => (isFlow ? setSelected(t.key) : enter(t.folder))}
                  onDoubleClick={() => isFlow && open(t.entry)}
                  onKeyDown={(e) => e.key === "Enter" && (isFlow ? open(t.entry) : enter(t.folder))}>
                  <div className="home-tile-box">
                    {isFlow
                      ? <FolderGlyph label={plural(t.entry.steps.length, "step")} tone={tone(t.entry)} />
                      : <FolderGlyph label="OfficeFlow" tone={t.tone} />}
                    {on && (
                      <button className="home-open" onClick={(e) => { e.stopPropagation(); open(t.entry); }}>
                        Open<Icon name="forward" size={14} />
                      </button>
                    )}
                  </div>
                  <div className="home-tile-name ellipsis">{isFlow ? t.entry.name : t.name}</div>
                  <div className="home-tile-sub ellipsis">
                    {isFlow ? `${flowFormats(t.entry, op) || kindLabel(t.entry)} · ${successRate(t.entry)}` : plural(t.count, "workflow")}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      <Deck subject={subject} runs={runs} workflows={library.saved.map((e) => ({ name: e.name, steps: e.steps }))}
        onOpen={() => current && open(current)}
        onOpenRun={(run) => run.kind === "operation" ? router.push(`/tool/?id=${run.target_id}`) : router.push(`/workflow/?name=${encodeURIComponent(run.target_id)}`)}
        onOpenWorkflow={(name) => router.push(name ? `/workflow/?name=${encodeURIComponent(name)}` : "/workflow/")}
        onNewRun={() => router.push("/workflow/")} />
    </div>
  );
}
