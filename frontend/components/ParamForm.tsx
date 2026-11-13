"use client";

import { useState } from "react";
import FileBrowser from "./FileBrowser";
import Icon from "./Icon";
import type { Param } from "@/lib/api";
import { nativePick } from "@/lib/pick";

export function defaults(params: Param[]): Record<string, unknown> {
  return Object.fromEntries(params.map((p) => [p.key, p.default]));
}

export function Check({ on, label, onChange }: { on: boolean; label: string; onChange(v: boolean): void }) {
  return (
    <div className={`check ${on ? "on" : ""}`} role="checkbox" aria-checked={on} tabIndex={0}
      onClick={() => onChange(!on)} onKeyDown={(e) => (e.key === " " || e.key === "Enter") && onChange(!on)}>
      <span className="box">{on && <Icon name="check" size={14} stroke={2.6} />}</span>
      <span>{label}</span>
    </div>
  );
}

export default function ParamForm({ params, values, onChange }: {
  params: Param[];
  values: Record<string, unknown>;
  onChange(values: Record<string, unknown>): void;
}) {
  const [browsing, setBrowsing] = useState<Param | null>(null);
  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value });
  if (!params.length) return <div className="muted">This tool has no settings.</div>;
  return (
    <div className="col" style={{ gap: 16 }}>
      {params.map((p) => {
        const value = values[p.key] ?? p.default;
        return (
          <div key={p.key} className="field">
            {p.type === "bool" ? (
              <Check on={Boolean(value)} label={p.label} onChange={(v) => set(p.key, v)} />
            ) : (
              <>
                <label>{p.label}{p.required && <span style={{ color: "var(--pink)" }}> *</span>}</label>
                {p.type === "multiline" ? (
                  <textarea className="textarea" value={String(value ?? "")} placeholder={p.placeholder} spellCheck={false}
                    onChange={(e) => set(p.key, e.target.value)} />
                ) : p.type === "choice" ? (
                  <select className="select" value={String(value)} onChange={(e) => set(p.key, e.target.value)}>
                    {p.choices.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                  </select>
                ) : p.type === "int" ? (
                  <input className="input" type="number" min={p.minimum} max={p.maximum} value={Number(value ?? 0)}
                    onChange={(e) => set(p.key, Number(e.target.value))} />
                ) : p.type === "file" ? (
                  <div className="row">
                    <input className="input" value={String(value ?? "")} placeholder={`Choose a ${p.extensions.join(", ")} file`}
                      onChange={(e) => set(p.key, e.target.value)} />
                    <button className="btn" onClick={async () => {
                      const picked = await nativePick("file", p.extensions);
                      if (picked === null) setBrowsing(p);
                      else if (picked[0]) set(p.key, picked[0]);
                    }}><Icon name="folder" size={17} />Browse</button>
                  </div>
                ) : (
                  <input className="input" value={String(value ?? "")} placeholder={p.placeholder} spellCheck={false}
                    onChange={(e) => set(p.key, e.target.value)} />
                )}
              </>
            )}
            {p.help && <div className="help">{p.help}</div>}
          </div>
        );
      })}
      {browsing && (
        <FileBrowser mode="file" extensions={browsing.extensions} onClose={() => setBrowsing(null)}
          onPick={(paths) => { set(browsing.key, paths[0]); setBrowsing(null); }} />
      )}
    </div>
  );
}
