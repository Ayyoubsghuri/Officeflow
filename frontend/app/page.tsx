"use client";

// Home: the workflow library as folder cards, with an Info panel on the right.
// Folder cards open in place (the path at the top goes back); a workflow card is
// selected with one click (its details show in Info) and opened with a double
// click, Enter, or the Open button.

import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { when } from "@/components/Deck";
import Icon from "@/components/Icon";
import { api, type Library, type LibraryEntry, type Operation } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { formats } from "@/lib/formats";
import {
  AI, RAN, allEntries, childFolders, flowFormats, folderTree, inFolder, kindLabel, matches, openHref, underFolder,
} from "@/lib/library";

type Filter = "all" | "saved" | "ai" | "run" | "never" | "failed";
const FILTERS: [Filter, string][] = [
  ["all", "All workflows"], ["saved", "Saved"], ["ai", "AI proposals"], ["run", "Ran, not saved"],
  ["never", "Never run"], ["failed", "Failed last time"],
];

type Card =
  | { type: "folder"; key: string; folder: string; name: string; entries: LibraryEntry[] }
  | { type: "flow"; key: string; entry: LibraryEntry };

const STATUS: Record<string, string> = { success: "Done", warning: "Done with remarks", failed: "Failed", cancelled: "Cancelled" };
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function keep(entry: LibraryEntry, filter: Filter): boolean {
  if (filter === "saved" || filter === "ai" || filter === "run") return entry.kind === filter;
  if (filter === "never") return entry.runs === 0;
  if (filter === "failed") return entry.last_status === "failed";
  return true;
}

function latest(entries: LibraryEntry[]): string {
  return entries.map((e) => e.last_run).filter(Boolean).sort().pop() ?? "";
}

/** A card shaped like a folder: back flap, sheets peeking out, glass front. */
function FolderCard({ title, sub, meta, sheet, selected, index, onClick, onOpen }: {
  title: string; sub: string; meta: string; sheet: string[]; selected: boolean; index: number;
  onClick(): void; onOpen(): void;
}) {
  return (
    <motion.div className={`fcard ${selected ? "on" : ""}`} role="button" tabIndex={0} title={title}
      initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
      transition={{ delay: Math.min(index, 12) * 0.03 }}
      onClick={onClick} onDoubleClick={onOpen} onKeyDown={(e) => e.key === "Enter" && onOpen()}>
      <div className="fcard-tab" />
      <div className="fcard-back" />
      <div className="fcard-sheet second" />
      <div className="fcard-sheet">{sheet.slice(0, 3).map((line, i) => <span key={i}>{line}</span>)}</div>
      <div className="fcard-front">
        <div className="fcard-title ellipsis">{title}</div>
        <div className="fcard-sub ellipsis">{sub}</div>
        <div className="grow" />
        <div className="fcard-meta ellipsis">{meta}</div>
      </div>
    </motion.div>
  );
}

function StatCard({ label, value, bar, tone, note }: { label: string; value: string; bar: number; tone: "good" | "bad"; note: string }) {
  return (
    <div className="info-stat">
      <div className="caption">{label}</div>
      <div className="info-value">{value}</div>
      <div className="info-bar"><motion.span className={tone} initial={{ width: 0 }} animate={{ width: `${Math.round(bar * 100)}%` }} /></div>
      <div className="info-note">{note}</div>
    </div>
  );
}

function ToolTags({ ids, op }: { ids: string[]; op: (id: string) => Operation | undefined }) {
  const unique = [...new Set(ids)];
  if (!unique.length) return <div className="muted" style={{ fontSize: 13 }}>No tools yet.</div>;
  return (
    <div className="info-tags">
      {unique.map((id) => {
        const tool = op(id);
        return <span key={id} className={`info-tag ${tool?.category ?? ""}`}>{tool?.name ?? id}</span>;
      })}
    </div>
  );
}

export default function Home() {
  const { meta, toast, op } = useApp();
  const router = useRouter();
  const [library, setLibrary] = useState<Library | null>(null);
  const [folder, setFolder] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState("");

  useEffect(() => {
    api<Library>("GET", "/api/library").then(setLibrary).catch((e) => toast(String(e), "error"));
  }, [toast]);

  const entries = useMemo(() => allEntries(library), [library]);
  const searching = query.trim().length > 0 || filter !== "all";

  const cards: Card[] = useMemo(() => {
    if (!library) return [];
    if (searching) {
      return entries.filter((e) => keep(e, filter) && matches(e, query, op)).map((entry) => ({ type: "flow", key: entry.key, entry }));
    }
    const out: Card[] = [];
    if (folder !== RAN && folder !== AI) {
      for (const f of childFolders(folderTree(library.folders), folder)) {
        out.push({ type: "folder", key: `dir:${f}`, folder: f, name: f.split("/").pop()!, entries: entries.filter((e) => underFolder(e, f)) });
      }
    }
    if (!folder) {
      if (library.ai.length) out.push({ type: "folder", key: "dir:ai", folder: AI, name: "AI proposals", entries: library.ai });
      if (library.recent.length) out.push({ type: "folder", key: "dir:ran", folder: RAN, name: "Ran, not saved", entries: library.recent });
      for (const entry of library.saved.filter((e) => !e.folder)) out.push({ type: "flow", key: entry.key, entry });
    } else {
      for (const entry of entries.filter((e) => inFolder(e, folder))) out.push({ type: "flow", key: entry.key, entry });
    }
    return out;
  }, [library, entries, folder, query, filter, searching, op]);

  const current = cards.find((c): c is Extract<Card, { type: "flow" }> => c.type === "flow" && c.key === selected)?.entry;
  const scope = useMemo(() => (folder === RAN || folder === AI ? entries.filter((e) => inFolder(e, folder))
    : folder ? entries.filter((e) => underFolder(e, folder)) : entries), [entries, folder]);

  const open = (entry: LibraryEntry) => router.push(openHref(entry));
  const enter = (f: string) => { setFolder(f); setSelected(""); setQuery(""); setFilter("all"); };
  const special = folder === RAN || folder === AI;
  const crumbs = folder === RAN ? ["Ran, not saved"] : folder === AI ? ["AI proposals"] : folder ? folder.split("/") : [];
  const parent = special || !folder.includes("/") ? "" : folder.slice(0, folder.lastIndexOf("/"));
  const title = searching ? (query.trim() ? `Results for “${query.trim()}”` : FILTERS.find(([f]) => f === filter)![1])
    : crumbs.length ? crumbs[crumbs.length - 1] : "Workflows";

  if (!meta || !library) return null;

  // ---- Info panel -------------------------------------------------------------
  const info = (() => {
    if (current) {
      const first = op(current.steps[0]);
      const last = op(current.steps[current.steps.length - 1]);
      const failed = current.runs - current.ok;
      const lastRun = current.last_run ? when(current.last_run) : null;
      return (
        <>
          <StatCard label="Runs" value={String(current.runs)} bar={current.runs ? current.ok / current.runs : 0} tone="good"
            note={current.runs ? `${Math.round((100 * current.ok) / current.runs)}% successful` : "Not run yet"} />
          <StatCard label="Failed runs" value={String(failed)} bar={current.runs ? failed / current.runs : 0} tone="bad"
            note={failed ? `Last result: ${STATUS[current.last_status] ?? current.last_status}` : "None"} />
          <div className="info-section">
            <div className="h3">Properties</div>
            <dl className="info-props">
              <dt>Folder</dt><dd>{kindLabel(current)}</dd>
              <dt>Steps</dt><dd>{current.steps.length}</dd>
              <dt>Reads</dt><dd>{first ? formats(first.input_extensions) : "—"}</dd>
              <dt>Writes</dt><dd>{last ? formats(last.output_extensions) : "—"}</dd>
              <dt>Last run</dt><dd>{lastRun ? `${lastRun.date} ${lastRun.time}` : "Never"}</dd>
              {current.updated_at && <><dt>Last change</dt><dd>{new Date(current.updated_at).toLocaleDateString()}</dd></>}
            </dl>
          </div>
          <div className="info-section">
            <div className="h3">Tools</div>
            <ToolTags ids={current.steps} op={op} />
          </div>
          {current.last_summary && <div className="info-summary">{current.last_summary}</div>}
          <div className="grow" />
          <button className="btn primary wide" onClick={() => open(current)}><Icon name="play" size={16} />Open workflow</button>
        </>
      );
    }
    const runs = scope.reduce((n, e) => n + e.runs, 0);
    const ok = scope.reduce((n, e) => n + e.ok, 0);
    const used = scope.filter((e) => e.runs > 0).length;
    const lastRun = latest(scope);
    const tools = Object.entries(scope.flatMap((e) => e.steps).reduce<Record<string, number>>((acc, id) => ({ ...acc, [id]: (acc[id] ?? 0) + 1 }), {}))
      .sort((a, b) => b[1] - a[1]).slice(0, 6).map(([id]) => id);
    return (
      <>
        <StatCard label="Workflows" value={String(scope.length)} bar={scope.length ? used / scope.length : 0} tone="good"
          note={`${used} of ${scope.length} used at least once`} />
        <StatCard label="Runs" value={String(runs)} bar={runs ? (runs - ok) / runs : 0} tone="bad"
          note={runs ? `${runs - ok} failed · ${Math.round((100 * ok) / runs)}% successful` : "Nothing run yet"} />
        <div className="info-section">
          <div className="h3">Properties</div>
          <dl className="info-props">
            <dt>Saved</dt><dd>{scope.filter((e) => e.kind === "saved").length}</dd>
            <dt>AI proposals</dt><dd>{scope.filter((e) => e.kind === "ai").length}</dd>
            <dt>Folders</dt><dd>{special ? 0 : childFolders(folderTree(library.folders), folder).length}</dd>
            <dt>Last run</dt><dd>{lastRun ? when(lastRun).ago : "Never"}</dd>
          </dl>
        </div>
        <div className="info-section">
          <div className="h3">Most used tools</div>
          <ToolTags ids={tools} op={op} />
        </div>
        <div className="grow" />
        <div className="info-links">
          <button onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={17} />Ask AI to build one</button>
          <button onClick={() => router.push("/history/")}><Icon name="history" size={17} />Activity</button>
        </div>
      </>
    );
  })();

  return (
    <div className="home">
      <main className="home-main">
        <div className="home-bar">
          <button className="btn icon ghost" title="Back" disabled={!folder && !searching}
            onClick={() => (searching ? (setQuery(""), setFilter("all")) : enter(parent))}><Icon name="back" size={18} /></button>
          <div className="home-crumbs">
            <button onClick={() => enter("")}><Icon name="folder" size={16} />Workflows</button>
            {!searching && crumbs.map((c, i) => (
              <span key={i} className="row" style={{ gap: 4 }}>
                <Icon name="forward" size={13} />
                <button className={i === crumbs.length - 1 ? "on" : ""}
                  onClick={() => !special && enter(crumbs.slice(0, i + 1).join("/"))}>
                  {i === crumbs.length - 1 && <Icon name="folder" size={16} />}{c}
                </button>
              </span>
            ))}
          </div>
          <div className="grow" />
          <button className="btn ghost" onClick={() => router.push(folder && !special ? `/workflows/?folder=${encodeURIComponent(folder)}` : "/workflows/")}>
            <Icon name="settings" size={16} />Manage
          </button>
        </div>

        <div className="row">
          <h1 className="h1 grow">{title}</h1>
          <button className="btn dark" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />New workflow</button>
        </div>

        <div className="row">
          <div className="lib-search" style={{ width: 300 }}>
            <Icon name="search" size={17} />
            <input className="input" value={query} placeholder="Search by name, folder or tool"
              onChange={(e) => { setQuery(e.target.value); setSelected(""); }} />
          </div>
          <div className="grow" />
          <label className={`btn filter ${filter !== "all" ? "on" : ""}`}>
            <Icon name="tidy" size={16} />
            <select value={filter} onChange={(e) => { setFilter(e.target.value as Filter); setSelected(""); }}>
              {FILTERS.map(([value, label]) => <option key={value} value={value}>{value === "all" ? "Filter" : label}</option>)}
            </select>
          </label>
        </div>

        {cards.length === 0 ? (
          <div className="lib-empty">
            <Icon name="folder" size={36} />
            <div>{searching ? "No workflow matches." : entries.length ? "This folder is empty."
              : "No workflow yet. Build one, or describe it to the AI assistant — it will appear here as a folder."}</div>
            <div className="row">
              <button className="btn primary" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />Build a workflow</button>
              <button className="btn pink" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={16} />Ask AI</button>
            </div>
          </div>
        ) : (
          <div className="fcards">
            <AnimatePresence mode="popLayout">
              {cards.map((card, i) => card.type === "folder" ? (
                <FolderCard key={`${folder}|${card.key}`} index={i} title={card.name} selected={false}
                  sub={plural(card.entries.length, "workflow")}
                  meta={card.entries.length ? `${plural(card.entries.reduce((n, e) => n + e.runs, 0), "run")}${latest(card.entries) ? ` · ${when(latest(card.entries)).ago}` : ""}` : "Empty"}
                  sheet={card.entries.slice(0, 3).map((e) => e.name)}
                  onClick={() => enter(card.folder)} onOpen={() => enter(card.folder)} />
              ) : (
                <FolderCard key={`${folder}|${card.key}`} index={i} title={card.entry.name} selected={current?.key === card.key}
                  sub={plural(card.entry.steps.length, "step")}
                  meta={flowFormats(card.entry, op) || kindLabel(card.entry)}
                  sheet={card.entry.steps.map((id) => op(id)?.name ?? id)}
                  onClick={() => setSelected(current?.key === card.key ? "" : card.key)} onOpen={() => open(card.entry)} />
              ))}
            </AnimatePresence>
          </div>
        )}
      </main>

      <aside className="info">
        <div className="row">
          <div className="h2 grow">Info</div>
          {current && <button className="btn icon ghost" title="Close" onClick={() => setSelected("")}><Icon name="x" size={16} /></button>}
        </div>
        <div className="info-name ellipsis">{current ? current.name : title}</div>
        {info}
      </aside>
    </div>
  );
}
