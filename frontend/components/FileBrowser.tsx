"use client";

// In-app file browser, used when no native dialog is available (browser mode).

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { api, type FolderListing } from "@/lib/api";

export default function FileBrowser({ mode, extensions, start, onPick, onClose }: {
  mode: "files" | "folder" | "file";
  extensions: string[];
  start?: string;
  onPick(paths: string[]): void;
  onClose(): void;
}) {
  const [listing, setListing] = useState<FolderListing | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [error, setError] = useState("");
  const load = async (path?: string) => {
    try {
      const query = new URLSearchParams({ path: path ?? "", extensions: extensions.join(",") });
      setListing(await api<FolderListing>("GET", `/api/fs/list?${query}`));
      setPicked([]);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  useEffect(() => {
    load(start);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const toggle = (path: string) => {
    if (mode === "file") return setPicked([path]);
    setPicked((p) => (p.includes(path) ? p.filter((x) => x !== path) : [...p, path]));
  };
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <motion.div className="card modal" initial={{ opacity: 0, y: 14, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
        onMouseDown={(e) => e.stopPropagation()}>
        <div className="row">
          <div className="h2 grow">{mode === "folder" ? "Choose a folder" : mode === "file" ? "Choose a file" : "Choose files"}</div>
          <button className="btn icon ghost" onClick={onClose}><Icon name="x" size={18} /></button>
        </div>
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          {listing?.roots.map((r) => <button key={r.path} className="tag" style={{ cursor: "pointer", border: "none" }} onClick={() => load(r.path)}>{r.name}</button>)}
        </div>
        <div className="row">
          <button className="btn icon" disabled={!listing?.parent} onClick={() => listing?.parent && load(listing.parent)}><Icon name="up" size={18} /></button>
          <input className="input selectable" value={listing?.path ?? ""} readOnly />
        </div>
        {error && <div className="banner failed">{error}</div>}
        <div className="tablewrap" style={{ maxHeight: "46vh", minHeight: 240 }}>
          <table className="table">
            <tbody>
              {listing?.entries.map((entry) => (
                <tr key={entry.path} className={`clickable ${picked.includes(entry.path) ? "selected" : ""}`}
                  onClick={() => (entry.dir ? (mode === "folder" ? setPicked([entry.path]) : load(entry.path)) : mode !== "folder" && toggle(entry.path))}
                  onDoubleClick={() => entry.dir && load(entry.path)}>
                  <td style={{ width: 34 }}><Icon name={entry.dir ? "folder" : entry.ext === ".pdf" ? "pdf" : entry.ext.startsWith(".xls") || entry.ext === ".csv" ? "excel" : entry.ext === ".docx" ? "word" : "file"} size={18} /></td>
                  <td>{entry.name}</td>
                  <td className="muted" style={{ width: 90, textAlign: "right" }}>{entry.dir ? "" : `${Math.max(1, Math.round(entry.size / 1024))} KB`}</td>
                </tr>
              ))}
              {listing && listing.entries.length === 0 && <tr><td className="muted">Nothing here.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="row">
          <span className="muted grow">{mode === "folder" ? "Double-click to open a folder, click to select it." : `${picked.length} selected`}</span>
          {mode === "folder" && <button className="btn" onClick={() => listing && onPick([listing.path])}>Use this folder</button>}
          <button className="btn primary" disabled={!picked.length} onClick={() => onPick(picked)}>Choose</button>
        </div>
      </motion.div>
    </div>
  );
}
