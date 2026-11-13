// File formats and which tools can follow which.

import type { Operation } from "./api";

const FAMILY: Record<string, string> = {
  ".xlsx": "Excel", ".xlsm": "Excel", ".csv": "CSV", ".tsv": "CSV", ".pdf": "PDF", ".docx": "Word",
  ".txt": "Text", ".html": "HTML",
};

export function family(ext: string): string {
  return FAMILY[ext] ?? ext.replace(".", "").toUpperCase();
}

export function formats(extensions: string[]): string {
  return Array.from(new Set(extensions.map(family))).join(" · ") || "Any";
}

export function canRead(op: Operation, available: string[] | null): boolean {
  if (available === null) return true; // nothing chosen yet: anything can start the flow
  return op.input_extensions.some((ext) => available.includes(ext));
}

/** Output types flowing out of step ``index`` (-1 = the start node). */
export function flowingOut(steps: Operation[], index: number, start: string[] | null): string[] | null {
  return index < 0 ? start : steps[index].output_extensions;
}

/** Is the whole chain readable from start to end? */
export function chainValid(steps: Operation[], start: string[] | null): boolean {
  return steps.every((op, i) => canRead(op, flowingOut(steps, i - 1, start)));
}
