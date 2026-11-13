"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";

export default function Logs() {
  const { toast } = useApp();
  const [level, setLevel] = useState("all");
  const [data, setData] = useState<{ lines: string[]; file: string }>({ lines: [], file: "" });
  const view = useRef<HTMLPreElement>(null);
  const load = () => api<{ lines: string[]; file: string }>("GET", `/api/logs?level=${level}`).then(setData).catch((e) => toast(String(e), "error"));
  useEffect(() => { load(); }, [level]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { view.current?.scrollTo(0, view.current.scrollHeight); }, [data]);
  return (
    <div className="col" style={{ gap: 18, height: "100%" }}>
      <div className="row">
        <div className="grow">
          <h1 className="h1">Logs and Error Reports</h1>
          <div className="muted" style={{ marginTop: 6 }}>Technical details of what the application did. Send this to your administrator if something goes wrong.</div>
        </div>
        <select className="select" style={{ width: 200 }} value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="all">All messages</option><option value="warnings">Warnings and errors</option><option value="errors">Errors only</option>
        </select>
        <button className="btn" onClick={load}><Icon name="refresh" size={17} />Refresh</button>
        <button className="btn" onClick={() => data.file && openPath(data.file.replace(/[\\/][^\\/]*$/, ""))}><Icon name="folder" size={17} />Open log folder</button>
      </div>
      <pre ref={view} className="card logs selectable">{data.lines.length ? data.lines.join("\n") : "No log entries."}</pre>
    </div>
  );
}
