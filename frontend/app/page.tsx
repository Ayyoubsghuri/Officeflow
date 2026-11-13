"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Deck from "@/components/Deck";
import FolderFan, { type FanItem } from "@/components/FolderFan";
import Icon from "@/components/Icon";
import { api, type Run } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { openPath } from "@/lib/desktop";

export default function Dashboard() {
  const { meta, stats, toast, refreshStats } = useApp();
  const router = useRouter();
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState("pdf.organize");
  const [runs, setRuns] = useState<Run[]>([]);
  const [workflows, setWorkflows] = useState<{ name: string; steps: string[] }[]>([]);

  useEffect(() => {
    refreshStats();
    api<Run[]>("GET", "/api/history?limit=6").then(setRuns).catch(() => {});
    api<{ name: string; steps: string[] }[]>("GET", "/api/workflows").then(setWorkflows).catch(() => {});
  }, [refreshStats]);

  const operations = useMemo(
    () => (meta?.operations ?? []).filter((o) => filter === "all" || o.category === filter),
    [meta, filter],
  );
  const items: FanItem[] = operations.map((op) => {
    const stat = stats?.targets[op.id];
    return {
      id: op.id, title: op.name, icon: op.category,
      caption: `${meta?.categories[op.category]} · ${stat ? stat.runs : 0} run${stat?.runs === 1 ? "" : "s"}`,
      stat: stat ? `${Math.round((100 * stat.ok) / stat.runs)}%` : "New",
    };
  });
  const current = operations.find((o) => o.id === selected) ?? operations[0];

  const exportHistory = async () => {
    try {
      const { path } = await api<{ path: string }>("POST", "/api/history/export");
      toast(`History exported to ${path}`);
      openPath(path).catch(() => {});
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };

  if (!meta) return null;
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="toolbar-row">
        {Object.entries(meta.categories).filter(([k]) => k !== "cross").map(([key, label]) => (
          <button key={key} className="chip" onClick={() => router.push(`/toolbox/?cat=${key}`)}>
            <Icon name={key} size={18} />{label} ({meta.operations.filter((o) => o.category === key).length})
          </button>
        ))}
        <label className="chip" style={{ position: "relative" }}>
          <Icon name="folder" size={18} />
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="chip-select">
            <option value="all">All tools</option>
            {Object.entries(meta.categories).filter(([k]) => k !== "cross").map(([k, v]) => <option key={k} value={k}>{v} only</option>)}
          </select>
          <Icon name="down" size={16} />
        </label>
        <div className="grow" />
        <button className="chip" onClick={exportHistory}><Icon name="export" size={18} />Export</button>
        <button className="chip" onClick={() => router.push("/history/")}><Icon name="tasks" size={18} />View tasks</button>
        <button className="chip" onClick={() => router.push("/workflow/")}><Icon name="plus" size={18} />New workflow</button>
      </div>
      <FolderFan items={items} selected={current?.id ?? ""} onSelect={setSelected}
        onOpen={(id) => router.push(`/tool/?id=${id}`)} />
      <Deck op={current} stat={current ? stats?.targets[current.id] : undefined} runs={runs} workflows={workflows}
        onOpen={() => current && router.push(`/tool/?id=${current.id}`)}
        onOpenRun={(run) => run.kind === "operation" ? router.push(`/tool/?id=${run.target_id}`) : router.push(`/workflow/?name=${encodeURIComponent(run.target_id)}`)}
        onOpenWorkflow={(name) => router.push(name ? `/workflow/?name=${encodeURIComponent(name)}` : "/workflow/")}
        onNewRun={() => current && router.push(`/tool/?id=${current.id}`)} />
    </div>
  );
}
