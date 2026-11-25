// Helpers shared by the workflow library and the dashboard.

import type { Library, LibraryEntry, Operation } from "./api";
import { formats } from "./formats";

export const RAN = "__ran__";
export const AI = "__ai__";
export const UNFILED = "__unfiled__";

export function allEntries(library: Library | null): LibraryEntry[] {
  return library ? [...library.saved, ...library.recent, ...library.ai] : [];
}

/** Text a workflow can be found by: name, folder and the names of its tools. */
export function matches(entry: LibraryEntry, query: string, op: (id: string) => Operation | undefined): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const text = [entry.name, entry.folder, ...entry.steps.map((id) => op(id)?.name ?? id)].join(" ").toLowerCase();
  return q.split(/\s+/).every((word) => text.includes(word));
}

export function inFolder(entry: LibraryEntry, folder: string): boolean {
  if (folder === RAN) return entry.kind === "run";
  if (folder === AI) return entry.kind === "ai";
  if (folder === UNFILED) return entry.kind === "saved" && !entry.folder;
  if (!folder) return true;
  return entry.kind === "saved" && entry.folder === folder;
}

export function underFolder(entry: LibraryEntry, folder: string): boolean {
  return entry.kind === "saved" && (entry.folder === folder || entry.folder.startsWith(folder + "/"));
}

export function folderTree(folders: string[]): string[] {
  // every parent of every folder, sorted so children follow their parent
  const all = new Set<string>();
  for (const folder of folders) {
    const parts = folder.split("/");
    for (let i = 1; i <= parts.length; i++) all.add(parts.slice(0, i).join("/"));
  }
  return [...all].sort((a, b) => a.localeCompare(b));
}

export function childFolders(tree: string[], parent: string): string[] {
  return tree.filter((f) => (parent ? f.startsWith(parent + "/") && !f.slice(parent.length + 1).includes("/") : !f.includes("/")));
}

export function flowFormats(entry: LibraryEntry, op: (id: string) => Operation | undefined): string {
  const first = op(entry.steps[0]);
  const last = op(entry.steps[entry.steps.length - 1]);
  return first && last ? `${formats(first.input_extensions)} → ${formats(last.output_extensions)}` : "";
}

export function kindLabel(entry: LibraryEntry): string {
  return entry.kind === "saved" ? (entry.folder || "Saved") : entry.kind === "run" ? "Ran, not saved" : "AI proposal";
}

export function successRate(entry: LibraryEntry): string {
  return entry.runs ? `${Math.round((100 * entry.ok) / entry.runs)}%` : "New";
}

/** Open a library workflow in the builder, ready to run. */
export function openHref(entry: LibraryEntry): string {
  if (entry.kind === "saved") return `/workflow/?name=${encodeURIComponent(entry.name)}`;
  sessionStorage.setItem("officeflow-ai-draft", JSON.stringify(entry.definition));
  return `/workflow/?draft=${entry.kind}`;
}
