"use client";

// Bottom of the dashboard: a dark deck with two tables and, in the middle, the
// selected tool as a green folder rising above the deck with glass sheets
// (its file formats) sticking out of it.

import { AnimatePresence, motion } from "framer-motion";
import Icon from "./Icon";
import type { Operation, Run, TargetStat } from "@/lib/api";
import { formats } from "@/lib/formats";

export function when(iso: string): { ago: string; date: string; time: string } {
  const date = new Date(iso);
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  const ago = minutes < 1 ? "Just now" : minutes < 60 ? `${minutes} min ago` : minutes < 1440 ? `${Math.round(minutes / 60)} h ago`
    : `${Math.round(minutes / 1440)} day${minutes < 2880 ? "" : "s"} ago`;
  return { ago, date: date.toLocaleDateString(), time: date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) };
}

const STATUS: Record<string, string> = { success: "Done", warning: "With remarks", failed: "Failed", cancelled: "Cancelled" };

/** What the green folder shows: a tool or a workflow. */
export interface DeckSubject {
  key: string;
  title: string;
  icon: string;
  reads: string;
  writes: string;
  detail: string;            // second line of the file row
  summary: string;           // last result, or a description
  runs: number;
  ok: number;
  lastRun: string;
  lastStatus: string;
  openLabel: string;
}

export function toolSubject(op: Operation, stat: TargetStat | undefined): DeckSubject {
  return {
    key: op.id, title: op.name, icon: op.category, reads: formats(op.input_extensions), writes: formats(op.output_extensions),
    detail: op.input_label, summary: stat ? stat.summary : op.description, runs: stat?.runs ?? 0, ok: stat?.ok ?? 0,
    lastRun: stat?.started_at ?? "", lastStatus: stat?.status ?? "", openLabel: "Open tool",
  };
}

export default function Deck({ subject, runs, workflows, onOpen, onOpenRun, onOpenWorkflow, onNewRun }: {
  subject: DeckSubject | undefined;
  runs: Run[];
  workflows: { name: string; steps: string[] }[];
  onOpen(): void;
  onOpenRun(run: Run): void;
  onOpenWorkflow(name: string): void;
  onNewRun(): void;
}) {
  const op = subject;
  const rate = op && op.runs ? Math.round((100 * op.ok) / op.runs) : 0;
  const sheets = op ? [...new Set([...op.reads.split(" · "), ...op.writes.split(" · ")])].slice(0, 3) : [];
  while (sheets.length < 3) sheets.push(["Preview", "Report", "Log"][sheets.length]);
  return (
    <div className="deck">
      <div className="deck-panel">
        <div className="deck-side">
          <div className="h2">Recent activity</div>
          <div className="muted" style={{ fontSize: 12 }}>Everything runs on this computer, offline.</div>
          <table className="deck-table">
            <thead><tr><th style={{ width: 54 }} /><th>Date</th><th>Task</th></tr></thead>
            <tbody>
              {runs.slice(0, 4).map((run, i) => {
                const t = when(run.started_at);
                return (
                  <tr key={run.id} onClick={() => onOpenRun(run)}>
                    <td>{i === 0 ? <button className="deck-plus" title="Run a tool" onClick={(e) => { e.stopPropagation(); onNewRun(); }}><Icon name="plus" size={16} /></button> : null}</td>
                    <td><div>{t.ago}</div><div className="faint" style={{ fontSize: 11 }}>{t.date}</div></td>
                    <td><div className="ellipsis">{run.name}</div><div className={`deck-status ${run.status}`}>{STATUS[run.status] ?? run.status}</div></td>
                  </tr>
                );
              })}
              {runs.length === 0 && (
                <tr><td><button className="deck-plus" onClick={onNewRun}><Icon name="plus" size={16} /></button></td>
                  <td colSpan={2} className="muted">No task yet — open a tool to start.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div />
        <div className="deck-side">
          <div className="h2" style={{ textAlign: "right" }}>Workflows</div>
          <div className="muted" style={{ fontSize: 12, textAlign: "right" }}>Saved automations, ready to run.</div>
          <table className="deck-table">
            <thead><tr><th>Workflow</th><th style={{ textAlign: "right" }}>Steps</th></tr></thead>
            <tbody>
              {workflows.slice(0, 4).map((w) => (
                <tr key={w.name} onClick={() => onOpenWorkflow(w.name)}>
                  <td className="ellipsis">{w.name}</td>
                  <td style={{ textAlign: "right" }}><span className="tag">{w.steps.length}</span></td>
                </tr>
              ))}
              {workflows.length === 0 && (
                <tr onClick={() => onOpenWorkflow("")}><td colSpan={2} className="muted">No workflow yet — <span style={{ color: "var(--accent-text)" }}>build one</span></td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {op && (
          <motion.div key={op.key} className="deck-folder" initial={{ y: 26, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
            exit={{ y: 16, opacity: 0 }} transition={{ type: "spring", stiffness: 260, damping: 26 }}>
            <div className="deck-sheets">
              {sheets.map((name, i) => (
                <motion.div key={name + i} className="deck-sheet" style={{ left: `${18 + i * 17}%`, top: 34 - i * 12, zIndex: i }}
                  initial={{ y: 30 }} animate={{ y: 0 }} transition={{ delay: 0.05 * i, type: "spring", stiffness: 300, damping: 24 }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span style={{ fontSize: 11 }}>{name}</span>
                    {i === 2 && <span className="deck-q"><Icon name="question" size={13} /></span>}
                  </div>
                  <div style={{ fontSize: 9, opacity: .7, marginTop: 8 }}>{i === 0 ? "Reads" : i === 1 ? "Writes" : "Creates"}</div>
                  <div style={{ fontSize: 11, fontWeight: 700 }}>{i === 0 ? op.reads : i === 1 ? op.writes : "Report"}</div>
                </motion.div>
              ))}
            </div>
            <svg className="deck-folder-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
              <defs>
                <linearGradient id="deckFront" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#43a869" /><stop offset=".55" stopColor="#3a9e60" /><stop offset="1" stopColor="#55bd7a" />
                </linearGradient>
              </defs>
              <path d="M0 26 Q0 20 4 20 L27 20 C37 20 36 30 47 30 L96 30 Q100 30 100 36 L100 100 L0 100 Z" fill="url(#deckFront)" />
            </svg>
            <div className="deck-folder-body">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div className="deck-title">{op.title}</div>
                  <div className="deck-sub">Recent activity</div>
                </div>
                <button className="btn white" onClick={onOpen}><Icon name="arrow" size={16} />{op.openLabel}</button>
              </div>
              <div className="deck-timeline">
                <div className="row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                  <span>{op.runs ? `${op.runs} run${op.runs > 1 ? "s" : ""} · ${when(op.lastRun).ago}` : "Not used yet"}</span>
                  <span>{op.runs ? `${rate}% completed` : op.icon === "workflow" ? "Not run yet" : "Preview first"}</span>
                </div>
                <div className="deck-line">
                  <motion.div className="deck-line-done" initial={{ width: 0 }} animate={{ width: `${op.runs ? rate : 0}%` }} />
                  <motion.span className="deck-marker" initial={{ left: 0 }} animate={{ left: `${op.runs ? rate : 0}%` }} />
                </div>
              </div>
              <div className="deck-file">
                <span className="deck-file-icon"><Icon name={op.icon} size={16} /></span>
                <div className="grow">
                  <div className="ellipsis" style={{ fontWeight: 600 }}>{op.reads} → {op.writes}</div>
                  <div className="ellipsis" style={{ fontSize: 12, opacity: .8 }}>{op.detail}</div>
                </div>
              </div>
              <div className="deck-row">
                <span className="deck-row-icon"><Icon name={op.lastStatus === "failed" ? "x" : "check"} size={15} /></span>
                <div className="grow ellipsis">{op.summary}</div>
                {op.lastRun && <span className="deck-time">{when(op.lastRun).time}</span>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
