"use client";

import { AnimatePresence, motion } from "framer-motion";
import Icon from "./Icon";
import { Check } from "./ParamForm";
import FileBrowser from "./FileBrowser";
import { useState } from "react";
import type { JobState } from "@/lib/api";
import { openPath } from "@/lib/desktop";
import { nativePick } from "@/lib/pick";

const TITLES: Record<string, string> = {
  success: "Done", warning: "Done — with remarks", failed: "Could not complete", cancelled: "Cancelled",
  info: "Preview — nothing has been changed",
};

export function ResultView({ job, error, maxRows = 400 }: { job: JobState | null; error: string; maxRows?: number }) {
  if (error) return <div className="banner failed"><b>Could not start</b><div className="muted">{error}</div></div>;
  if (!job || job.state === "running") return null;
  if (job.state === "error") return <div className="banner failed"><b>Could not complete</b><div>{job.error}</div></div>;
  const r = job.result!;
  const notes = [...r.errors.filter((e) => e !== r.summary).map((e) => `✕ ${e}`), ...r.warnings];
  return (
    <motion.div className="col" style={{ gap: 12 }} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <div className={`banner ${r.status}`}>
        <div className="row">
          <b className="grow">{TITLES[r.status] ?? r.status}</b>
          {r.status !== "failed" && r.status !== "info" && (
            <button className="btn" onClick={() => openPath(r.result_dir || job.output_dir)}><Icon name="folder" size={16} />Open output folder</button>
          )}
        </div>
        <div style={{ marginTop: 6 }}>{r.summary}</div>
        {notes.length > 0 && (
          <ul>
            {notes.slice(0, 8).map((n, i) => <li key={i}>{n}</li>)}
            {notes.length > 8 && <li>… and {notes.length - 8} more (see Logs)</li>}
          </ul>
        )}
      </div>
      {r.rows.length > 0 && (
        <div className="tablewrap selectable">
          <table className="table">
            <thead><tr>{r.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>
              {r.rows.slice(0, maxRows).map((row, i) => (
                <tr key={i}>{row.map((cell, j) => <td key={j} title={cell}>{cell}</td>)}</tr>
              ))}
            </tbody>
          </table>
          {r.total_rows > Math.min(maxRows, r.rows.length) && <div className="muted" style={{ padding: 10 }}>Showing {Math.min(maxRows, r.rows.length)} of {r.total_rows} rows.</div>}
        </div>
      )}
    </motion.div>
  );
}

export function Progress({ job }: { job: JobState | null }) {
  if (!job || job.state !== "running") return null;
  const { done, total, message } = job.progress;
  const pct = total ? (100 * done) / total : 0;
  return (
    <div className="col" style={{ gap: 6 }}>
      <div className={`progress ${total ? "" : "indeterminate"}`}><div style={{ width: `${pct}%` }} /></div>
      <div className="muted" style={{ fontSize: 13 }}>{message}{total && !message.startsWith("Step") ? `  (${done}/${total})` : ""}</div>
    </div>
  );
}

export default function RunPanel({ outputDir, onOutputDir, recursive, onRecursive, onPreview, onRun, onCancel, job, error, runLabel = "Run",
  keepIntermediate, onKeepIntermediate }: {
  outputDir: string; onOutputDir(v: string): void;
  recursive: boolean; onRecursive(v: boolean): void;
  keepIntermediate?: boolean; onKeepIntermediate?(v: boolean): void;
  onPreview?(): void; onRun(): void; onCancel(): void;
  job: JobState | null; error: string; runLabel?: string;
}) {
  const [browsing, setBrowsing] = useState(false);
  const running = job?.state === "running";
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="field">
        <label>Output folder</label>
        <div className="row">
          <input className="input" value={outputDir} onChange={(e) => onOutputDir(e.target.value)} />
          <button className="btn" onClick={async () => {
            const picked = await nativePick("folder", [], outputDir);
            if (picked === null) setBrowsing(true);
            else if (picked[0]) onOutputDir(picked[0]);
          }}><Icon name="folder" size={17} />Browse</button>
        </div>
        <div className="help">Results are written here. Your original files are never modified and existing files are never overwritten.</div>
      </div>
      <Check on={recursive} label="Include files in sub-folders" onChange={onRecursive} />
      {onKeepIntermediate && (
        <>
          <Check on={!!keepIntermediate} label="Keep intermediate files of each step" onChange={onKeepIntermediate} />
          <div className="help" style={{ marginTop: -8 }}>Off: only the final result is saved, in one folder named after the workflow.</div>
        </>
      )}
      <div className="row">
        {onPreview && <button className="btn" disabled={running} onClick={onPreview}><Icon name="eye" size={17} />Preview</button>}
        <button className="btn primary" disabled={running} onClick={onRun}><Icon name="play" size={16} />{runLabel}</button>
        <AnimatePresence>
          {running && (
            <motion.button className="btn danger" initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} onClick={onCancel}>
              <Icon name="stop" size={16} />Cancel
            </motion.button>
          )}
        </AnimatePresence>
      </div>
      <Progress job={job} />
      <ResultView job={job} error={error} />
      {browsing && <FileBrowser mode="folder" extensions={[]} start={outputDir} onClose={() => setBrowsing(false)}
        onPick={(p) => { onOutputDir(p[0]); setBrowsing(false); }} />}
    </div>
  );
}
