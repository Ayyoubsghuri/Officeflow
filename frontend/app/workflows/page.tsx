"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { when } from "@/components/Deck";
import FolderGlyph from "@/components/FolderGlyph";
import Icon from "@/components/Icon";
import { api, type Library, type LibraryEntry } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import {
  AI, RAN, UNFILED, allEntries, childFolders, flowFormats, folderTree, inFolder, kindLabel, matches, openHref,
  successRate, underFolder,
} from "@/lib/library";

const STATUS: Record<string, [string, string]> = {
  success: ["Done", "green"], warning: ["Remarks", "amber"], failed: ["Failed", "red"], cancelled: ["Cancelled", ""],
};

function tone(entry: LibraryEntry): "grey" | "green" | "amber" | "blue" {
  if (entry.kind === "ai") return "blue";
  if (entry.last_status === "failed") return "amber";
  return entry.runs ? "green" : "grey";
}

function folderName(folder: string): string {
  if (folder === RAN) return "Ran, not saved";
  if (folder === AI) return "AI proposals";
  if (folder === UNFILED) return "Not in a folder";
  return folder ? folder.split("/").pop()! : "All workflows";
}

function WorkflowLibrary() {
  const { op, toast } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [library, setLibrary] = useState<Library | null>(null);
  const [folder, setFolder] = useState(params.get("folder") ?? "");
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [tab, setTab] = useState<"folders" | "recent">("folders");

  const load = useCallback(() => api<Library>("GET", "/api/library").then(setLibrary).catch((e) => toast(String(e), "error")), [toast]);
  useEffect(() => { load(); }, [load]);

  const entries = useMemo(() => allEntries(library), [library]);
  const tree = useMemo(() => folderTree(library?.folders ?? []), [library]);
  const searching = query.trim().length > 0;
  const shown = useMemo(() => entries.filter((e) => (searching ? true : inFolder(e, folder)) && matches(e, query, op)),
    [entries, folder, query, searching, op]);
  const subfolders = searching || folder === RAN || folder === AI || folder === UNFILED ? [] : childFolders(tree, folder);
  const recent = useMemo(() => entries.filter((e) => e.last_run).sort((a, b) => b.last_run.localeCompare(a.last_run)).slice(0, 12), [entries]);

  const count = (f: string) => entries.filter((e) => underFolder(e, f)).length;
  const open = (entry: LibraryEntry) => router.push(openHref(entry));
  const move = async (entry: LibraryEntry) => {
    const target = window.prompt(`Move “${entry.name}” to which folder? Use / for sub-folders, leave empty for none.`, entry.folder);
    if (target === null) return;
    try {
      await api("POST", `/api/workflows/${encodeURIComponent(entry.name)}/move`, { folder: target });
      toast(target.trim() ? `Moved to ${target.trim()}.` : "Removed from its folder.");
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };
  const renameFolder = async (old: string) => {
    const next = window.prompt(`Rename the folder “${old}” (its sub-folders follow):`, old);
    if (!next || next === old) return;
    try {
      const { folder: renamed } = await api<{ folder: string }>("POST", "/api/folders/rename", { old, new: next });
      setFolder(renamed);
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  const TreeItem = ({ value, depth = 0, icon = "folder", label, n }: { value: string; depth?: number; icon?: string; label: string; n: number }) => (
    <button className={`tree-item ${folder === value && !searching ? "on" : ""}`} style={{ paddingLeft: 10 + depth * 18 }}
      onClick={() => { setFolder(value); setQuery(""); }}>
      {depth > 0 && <span className="guide" style={{ left: depth * 18 - 6 }} />}
      <Icon name={icon} size={17} /><span className="ellipsis">{label}</span>{n > 0 && <span className="count">{n}</span>}
    </button>
  );

  if (!library) return null;
  return (
    <div className="library">
      <aside className="card lib-side">
        <div className="row">
          <div className="h2 grow">Workflows</div>
          <button className="btn icon ghost" title="New workflow" onClick={() => router.push("/workflow/")}><Icon name="plus" size={18} /></button>
          <button className="btn icon ghost" title="Ask the AI to build one" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={17} /></button>
        </div>
        <div className="lib-search">
          <Icon name="search" size={17} />
          <input className="input" placeholder="Search workflows…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="segmented" style={{ alignSelf: "stretch" }}>
          {(["folders", "recent"] as const).map((t) => (
            <button key={t} className={tab === t ? "on" : ""} style={{ flex: 1, justifyContent: "center" }} onClick={() => setTab(t)}>
              {t === "folders" ? "Folders" : "Recent"}
              {tab === t && <motion.span layoutId="libtab" className="seg-bg" />}
            </button>
          ))}
        </div>
        {tab === "folders" ? (
          <div className="tree">
            <TreeItem value="" icon="home" label="All workflows" n={entries.length} />
            {tree.map((f) => <TreeItem key={f} value={f} depth={f.split("/").length - 1} label={f.split("/").pop()!} n={count(f)} />)}
            {library.saved.some((e) => !e.folder) && <TreeItem value={UNFILED} icon="file" label="Not in a folder" n={library.saved.filter((e) => !e.folder).length} />}
            <div className="tree-sep" />
            <TreeItem value={RAN} icon="history" label="Ran, not saved" n={library.recent.length} />
            <TreeItem value={AI} icon="sparkle" label="AI proposals" n={library.ai.length} />
          </div>
        ) : (
          <div className="tree">
            {recent.length === 0 && <div className="muted" style={{ padding: 8 }}>No workflow has been run yet.</div>}
            {recent.map((e) => (
              <button key={e.key} className="tree-item" onClick={() => open(e)} title={e.last_summary}>
                <Icon name="workflow" size={16} />
                <span className="ellipsis">{e.name}</span>
                <span className="count">{when(e.last_run).ago.replace(" ago", "")}</span>
              </button>
            ))}
          </div>
        )}
      </aside>

      <main className="lib-main">
        <div className="row">
          <div className="grow">
            <h1 className="h1">{searching ? `Results for “${query}”` : folderName(folder)}</h1>
            <div className="muted" style={{ marginTop: 4 }}>
              {searching ? `${shown.length} workflow(s) found by name, folder or tool.` : "Click a workflow to open it ready to run. Saved, already run, or proposed by the AI."}
            </div>
          </div>
          {folder && !searching && folder !== RAN && folder !== AI && folder !== UNFILED && (
            <button className="btn" onClick={() => renameFolder(folder)}><Icon name="folder" size={16} />Rename folder</button>
          )}
          <button className="btn primary" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />New workflow</button>
        </div>

        {subfolders.length > 0 && (
          <section className="col" style={{ gap: 10 }}>
            <div className="h2">Folders</div>
            <div className="lib-grid">
              {subfolders.map((f, i) => (
                <motion.button key={f} className="lib-card" onClick={() => setFolder(f)}
                  initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                  <FolderGlyph label="OfficeFlow" />
                  <div className="name ellipsis">{f.split("/").pop()}</div>
                  <div className="sub">{count(f)} workflow{count(f) === 1 ? "" : "s"}</div>
                </motion.button>
              ))}
            </div>
          </section>
        )}

        <section className="col" style={{ gap: 10 }}>
          {subfolders.length > 0 && <div className="h2">Workflows</div>}
          {shown.length === 0 ? (
            <div className="card lib-empty">
              <FolderGlyph size="lg" />
              <div>{searching ? "No workflow matches your search." : entries.length ? "This folder is empty." : "No workflow yet. Build one, or describe it to the AI assistant."}</div>
              <div className="row">
                <button className="btn primary" onClick={() => router.push("/workflow/")}><Icon name="plus" size={16} />Build a workflow</button>
                <button className="btn pink" onClick={() => router.push("/assistant/?mode=workflow")}><Icon name="sparkle" size={16} />Ask AI</button>
              </div>
            </div>
          ) : (
            <div className="lib-grid">
              <AnimatePresence>
                {shown.map((entry, i) => (
                  <motion.div key={entry.key} className="lib-card" role="button" tabIndex={0} onClick={() => open(entry)}
                    onKeyDown={(e) => e.key === "Enter" && open(entry)} title={entry.last_summary || entry.name}
                    initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ delay: Math.min(i, 12) * 0.025 }}>
                    {entry.kind === "saved" && (
                      <div className="menu" onClick={(e) => e.stopPropagation()}>
                        <button title="Move to another folder" onClick={() => move(entry)}><Icon name="folder" size={15} /></button>
                      </div>
                    )}
                    <FolderGlyph label={`${entry.steps.length} step${entry.steps.length === 1 ? "" : "s"}`} tone={tone(entry)} />
                    <div className="name ellipsis">{entry.name}</div>
                    <div className="sub ellipsis">{flowFormats(entry, op)}</div>
                    <div className="pillrow">
                      <span className="tag">{kindLabel(entry)}</span>
                      <span className={`tag ${entry.runs ? (entry.last_status === "failed" ? "red" : "green") : ""}`}>{successRate(entry)}</span>
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </section>

        {recent.length > 0 && !searching && (
          <section className="col" style={{ gap: 10 }}>
            <div className="h2">Recently run</div>
            <div className="tablewrap">
              <table className="table">
                <thead><tr><th>Workflow</th><th>Folder</th><th>Steps</th><th>Last run</th><th>Result</th></tr></thead>
                <tbody>
                  {recent.map((e) => (
                    <tr key={e.key} className="clickable" onClick={() => open(e)}>
                      <td><Icon name="workflow" size={14} /> {e.name}</td>
                      <td className="muted">{kindLabel(e)}</td>
                      <td>{e.steps.map((id) => op(id)?.name ?? id).join(" → ")}</td>
                      <td>{when(e.last_run).ago}</td>
                      <td><span className={`tag ${STATUS[e.last_status]?.[1] ?? ""}`}>{STATUS[e.last_status]?.[0] ?? e.last_status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default function Page() {
  return <Suspense><WorkflowLibrary /></Suspense>;
}
