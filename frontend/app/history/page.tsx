"use client";

import { useEffect, useState } from "react";
import { when } from "@/components/Deck";
import Icon from "@/components/Icon";
import { api, type Run } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";

const STATUS: Record<string, [string, string]> = {
  success: ["Done", "green"], warning: ["Remarks", "amber"], failed: ["Failed", "red"], cancelled: ["Cancelled", ""],
};

export default function History() {
  const { toast, refreshStats } = useApp();
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<Run | null>(null);
  const [filter, setFilter] = useState("all");
  const load = () => api<Run[]>("GET", "/api/history?limit=1000").then(setRuns).catch((e) => toast(String(e), "error"));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const shown = runs.filter((r) => filter === "all" || r.status === filter);
  const notes = selected ? [
    ...(selected.details.errors ?? []).map((e) => `✕ ${e}`), ...(selected.details.warnings ?? []).map((w) => `• ${w}`),
    ...(selected.details.steps ?? []).flatMap((s) => [`${s.name}: ${s.summary}`, ...s.errors.map((e) => `   ✕ ${e}`), ...s.warnings.map((w) => `   • ${w}`)]),
  ] : [];
  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="row">
        <div className="grow">
          <h1 className="h1">Processing History</h1>
          <div className="muted" style={{ marginTop: 6 }}>Every task that was run, with its result.</div>
        </div>
        <select className="select" style={{ width: 170 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All results</option><option value="success">Done</option><option value="warning">With remarks</option>
          <option value="failed">Failed</option><option value="cancelled">Cancelled</option>
        </select>
        <button className="btn" onClick={async () => {
          const { path } = await api<{ path: string }>("POST", "/api/history/export");
          toast(`Exported to ${path}`);
        }}><Icon name="export" size={17} />Export</button>
        <button className="btn danger" onClick={async () => {
          if (!window.confirm("Remove all entries from the history? Your files are not affected.")) return;
          await api("DELETE", "/api/history");
          setSelected(null);
          load();
          refreshStats();
        }}><Icon name="trash" size={16} />Clear</button>
      </div>
      <div className="history">
        <div className="card" style={{ overflow: "hidden" }}>
          <div className="tablewrap" style={{ border: "none", maxHeight: "calc(100vh - 260px)" }}>
            <table className="table">
              <thead><tr><th>When</th><th>Task</th><th>Status</th><th>In</th><th>Out</th><th>Result</th></tr></thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.id} className={`clickable ${selected?.id === r.id ? "selected" : ""}`} onClick={() => setSelected(r)}>
                    <td>{when(r.started_at).date} {when(r.started_at).time}</td>
                    <td>{r.kind === "workflow" && <Icon name="workflow" size={14} />} {r.name}</td>
                    <td><span className={`tag ${STATUS[r.status]?.[1] ?? ""}`}>{STATUS[r.status]?.[0] ?? r.status}</span></td>
                    <td>{r.input_count}</td><td>{r.output_count}</td><td title={r.summary}>{r.summary}</td>
                  </tr>
                ))}
                {shown.length === 0 && <tr><td colSpan={6} className="muted" style={{ padding: 24 }}>Nothing here yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card pad col" style={{ alignSelf: "start" }}>
          <div className="caption">Details</div>
          {selected ? (
            <>
              <div className="h2">{selected.name}</div>
              <div className="muted">{selected.summary}</div>
              <div className="faint selectable" style={{ fontSize: 12, wordBreak: "break-all" }}>{selected.output_dir}</div>
              <button className="btn" onClick={() => openPath(selected.output_dir).catch((e) => toast(String(e), "error"))}><Icon name="folder" size={16} />Open output folder</button>
              <div className="selectable" style={{ whiteSpace: "pre-wrap", fontSize: 13, color: "var(--muted)", maxHeight: 360, overflow: "auto" }}>
                {notes.length ? notes.join("\n") : "No warnings or errors."}
              </div>
            </>
          ) : <div className="muted">Select a task to see its warnings and errors.</div>}
        </div>
      </div>
    </div>
  );
}
