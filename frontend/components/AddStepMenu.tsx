"use client";

import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import Icon from "./Icon";
import type { Operation } from "@/lib/api";
import { formats } from "@/lib/formats";

/** Lists only the tools that can take the files flowing at this point of the chain. */
export default function AddStepMenu({ operations, categories, reads, feeds, position, onPick, onClose }: {
  operations: Operation[];
  categories: Record<string, string>;
  reads: string[] | null;          // what arrives here (null = anything: no input chosen yet)
  feeds: Operation | null;          // the step after the insertion point, which must read our output
  position: { x: number; y: number };
  onPick(op: Operation): void;
  onClose(): void;
}) {
  const [query, setQuery] = useState("");
  const options = useMemo(() => operations.filter((op) =>
    (reads === null || op.input_extensions.some((e) => reads.includes(e)))
    && (!feeds || op.output_extensions.some((e) => feeds.input_extensions.includes(e)))
    && `${op.name} ${op.description}`.toLowerCase().includes(query.toLowerCase())), [operations, reads, feeds, query]);
  const groups = Object.keys(categories).map((key) => [key, options.filter((o) => o.category === key)] as const).filter(([, list]) => list.length);
  return (
    <div className="menu-backdrop" onMouseDown={onClose}>
      <motion.div className="card addmenu" style={{ left: position.x, top: position.y }} initial={{ opacity: 0, y: 8, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="addmenu-head">
          <div className="caption">Add a step</div>
          <div className="fmt" style={{ marginTop: 4 }}>
            {reads === null ? <>Any tool can start the flow</> : <>Must read <b>{formats(reads)}</b></>}
            {feeds && <> · must produce <b>{formats(feeds.input_extensions)}</b> for “{feeds.name}”</>}
          </div>
          <input className="input" autoFocus placeholder="Search…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ marginTop: 10 }} />
        </div>
        <div className="addmenu-list">
          {groups.map(([key, list]) => (
            <div key={key}>
              <div className="caption" style={{ padding: "10px 12px 4px" }}>{categories[key]}</div>
              {list.map((op) => (
                <button key={op.id} className={`addmenu-item cat-${op.category}`} onClick={() => onPick(op)}>
                  <span className="tile small"><Icon name={op.category} size={16} /></span>
                  <span className="grow ellipsis">{op.name}</span>
                  <span className="fmt"><b>{formats(op.input_extensions)}</b>→<b>{formats(op.output_extensions)}</b></span>
                </button>
              ))}
            </div>
          ))}
          {groups.length === 0 && (
            <div className="muted" style={{ padding: 16 }}>
              {query ? "No matching tool." : `No tool can read ${formats(reads ?? [])} files${feeds ? ` and produce what “${feeds.name}” needs` : ""}.`}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
