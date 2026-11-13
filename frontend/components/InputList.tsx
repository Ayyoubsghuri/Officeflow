"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import FileBrowser from "./FileBrowser";
import Icon from "./Icon";
import { useApp } from "@/lib/app-context";
import { formats } from "@/lib/formats";
import { nativePick, type PickMode } from "@/lib/pick";

function nameOf(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

export default function InputList({ title, extensions, value, onChange }: {
  title: string;
  extensions: string[];
  value: string[];
  onChange(paths: string[]): void;
}) {
  const { settings, saveSettings, toast } = useApp();
  const [browser, setBrowser] = useState<PickMode | null>(null);
  const [hover, setHover] = useState(false);
  const zone = useRef<HTMLDivElement>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  const add = (paths: string[]) => {
    const accepted = paths.filter((p) => {
      const ext = p.includes(".") ? `.${p.split(".").pop()!.toLowerCase()}` : "";
      const looksLikeFile = /\.[a-z0-9]{2,5}$/i.test(p);
      return !looksLikeFile || !extensions.length || extensions.includes(ext);
    });
    if (accepted.length < paths.length) toast(`Only ${formats(extensions)} files are accepted here.`, "error");
    const next = [...valueRef.current];
    for (const p of accepted) if (!next.includes(p)) next.push(p);
    onChange(next);
    const first = accepted[0];
    if (first) saveSettings({ last_input_dir: /\.[a-z0-9]{2,5}$/i.test(first) ? first.replace(/[\\/][^\\/]*$/, "") : first });
  };

  // Files dropped from Explorer arrive from the desktop shell with full paths.
  useEffect(() => {
    const onDrop = (event: Event) => {
      const { paths, x, y } = (event as CustomEvent<{ paths: string[]; x: number; y: number }>).detail;
      const rect = zone.current?.getBoundingClientRect();
      if (rect && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom) add(paths);
      setHover(false);
    };
    window.addEventListener("officeflow-drop", onDrop);
    return () => window.removeEventListener("officeflow-drop", onDrop);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [extensions]);

  const pick = async (mode: PickMode) => {
    const paths = await nativePick(mode, extensions, settings?.last_input_dir ?? "");
    if (paths === null) setBrowser(mode);
    else if (paths.length) add(paths);
  };

  const move = (from: number, to: number) => {
    if (to < 0 || to >= value.length) return;
    const next = [...value];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  return (
    <div className="col" style={{ gap: 10 }}>
      <div className="row">
        <b className="grow">{title}</b>
        <span className="fmt">Accepts <b>{formats(extensions)}</b></span>
      </div>
      <div ref={zone} className={`dropzone ${hover ? "hover" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setHover(true); }} onDragLeave={() => setHover(false)}
        onDrop={(e) => {
          e.preventDefault();
          setHover(false);
          if (!(window as Window & { pywebview?: unknown }).pywebview) toast("Drag and drop works in the desktop app. Use “Files” or “Folder” here.", "error");
        }}>
        {value.length === 0 ? (
          <div className="dropzone-empty">
            <Icon name="folder" size={28} />
            <div>Drop files or folders here</div>
            <div className="faint" style={{ fontSize: 12 }}>or use the buttons below</div>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {value.map((path, i) => (
              <motion.div key={path} className="drop-item" layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 8 }}>
                <Icon name={/\.[a-z0-9]{2,5}$/i.test(path) ? "file" : "folder"} size={17} />
                <div className="grow" title={path}>
                  <div className="ellipsis">{nameOf(path)}</div>
                  <div className="faint ellipsis" style={{ fontSize: 11 }}>{path}</div>
                </div>
                <button className="btn icon ghost" title="Move up" onClick={() => move(i, i - 1)} disabled={i === 0}><Icon name="up" size={16} /></button>
                <button className="btn icon ghost" title="Remove" onClick={() => onChange(value.filter((p) => p !== path))}><Icon name="x" size={16} /></button>
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>
      <div className="row">
        <button className="btn" onClick={() => pick("files")}><Icon name="plus" size={17} />Files</button>
        <button className="btn" onClick={() => pick("folder")}><Icon name="folder" size={17} />Folder</button>
        <div className="grow" />
        {value.length > 0 && <button className="btn ghost" onClick={() => onChange([])}><Icon name="trash" size={16} />Clear</button>}
      </div>
      {browser && (
        <FileBrowser mode={browser} extensions={extensions} start={settings?.last_input_dir}
          onClose={() => setBrowser(null)} onPick={(paths) => { setBrowser(null); add(paths); }} />
      )}
    </div>
  );
}
