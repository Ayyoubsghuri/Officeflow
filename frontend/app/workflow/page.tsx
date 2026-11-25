"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import AddStepMenu from "@/components/AddStepMenu";
import FlowCanvas, { type CanvasHandle, type FlowNode } from "@/components/FlowCanvas";
import Icon from "@/components/Icon";
import InputList from "@/components/InputList";
import ParamForm, { defaults } from "@/components/ParamForm";
import RunPanel from "@/components/RunPanel";
import { api, type Operation, type WorkflowDef } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { canRead, chainValid, flowingOut, formats } from "@/lib/formats";
import { useJob } from "@/lib/useJob";

interface StepState {
  uid: string;
  op: string;
  params: Record<string, unknown>;
}
interface Snapshot {
  name: string;
  steps: StepState[];
}

let counter = 0;
const uid = () => `s${++counter}`;
const START = "start";

const TONES: Record<string, [string, string]> = {
  success: ["Done", "green"], warning: ["Remarks", "amber"], failed: ["Failed", "red"], cancelled: ["Cancelled", ""],
  running: ["Running…", "pinkish"], pending: ["Not run", ""],
};

function summary(op: Operation, params: Record<string, unknown>): string {
  for (const p of op.params) {
    const value = String(params[p.key] ?? p.default ?? "").trim();
    if ((p.type === "text" || p.type === "multiline" || p.type === "file") && value) {
      const shown = p.type === "file" ? value.split(/[\\/]/).pop() : value.split("\n")[0];
      return `${p.label.split("(")[0].trim()}: ${shown}`;
    }
  }
  return op.description.split(/(?<=[.:;])\s/)[0].replace(/\.$/, "");
}

function Builder() {
  const { meta, op: find, settings, toast } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<StepState[]>([]);
  const [selected, setSelected] = useState(START);
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [inputs, setInputs] = useState<string[]>([]);
  const [startExts, setStartExts] = useState<string[] | null>(null);
  const [saved, setSaved] = useState<string | null>(null);   // JSON of the saved definition
  const [savedList, setSavedList] = useState<{ name: string; folder: string; steps: string[] }[]>([]);
  const [folder, setFolder] = useState("");
  const [savedFolder, setSavedFolder] = useState<string | null>(null);
  const [undo, setUndo] = useState<Snapshot[]>([]);
  const [redo, setRedo] = useState<Snapshot[]>([]);
  const [menu, setMenu] = useState<{ at: { x: number; y: number }; index: number } | null>(null);
  const [outputDir, setOutputDir] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [keepIntermediate, setKeepIntermediate] = useState(false);
  const [runUids, setRunUids] = useState<string[]>([]);
  const editing = useRef("");
  const canvas = useRef<CanvasHandle>(null);
  const { job, error, start, cancel, setError } = useJob();

  const ops = useMemo(() => steps.map((s) => find(s.op)).filter(Boolean) as Operation[], [steps, find]);
  const definition = useCallback((): WorkflowDef => ({ name: name.trim(), steps: steps.map((s) => ({ op: s.op, params: s.params })) }), [name, steps]);
  const isSaved = saved !== null && saved === JSON.stringify(definition()) && (savedFolder ?? "") === folder.trim();

  useEffect(() => {
    if (settings) {
      setOutputDir((d) => d || settings.output_dir);
      setRecursive(settings.include_subfolders);
    }
  }, [settings]);

  const reloadList = useCallback(() => api<{ name: string; folder: string; steps: string[] }[]>("GET", "/api/workflows").then(setSavedList).catch(() => {}), []);
  useEffect(() => { reloadList(); }, [reloadList]);

  const load = useCallback(async (workflowName: string) => {
    try {
      const data = await api<WorkflowDef>("GET", `/api/workflows/${encodeURIComponent(workflowName)}`);
      setName(data.name);
      setFolder(data.folder ?? "");
      setSavedFolder(data.folder ?? "");
      setSteps(data.steps.map((s) => ({ uid: uid(), op: s.op, params: { ...s.params } })));
      setSaved(JSON.stringify({ name: data.name, steps: data.steps.map((s) => ({ op: s.op, params: s.params })) }));
      setSelected(START);
      setPositions({});
      setUndo([]);
      setRedo([]);
      setRunUids([]);
      setTimeout(() => canvas.current?.fit(), 50);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [toast]);

  useEffect(() => {
    const wanted = params.get("name");
    if (wanted && meta) load(wanted);
  }, [params, meta, load]);

  // A workflow proposed by the AI assistant opens here as an unsaved draft.
  useEffect(() => {
    const kind = params.get("draft");
    if (!kind || !meta) return;
    const raw = sessionStorage.getItem("officeflow-ai-draft");
    if (!raw) return;
    sessionStorage.removeItem("officeflow-ai-draft");
    try {
      const draft = JSON.parse(raw) as WorkflowDef;
      setName(draft.name);
      setFolder("");
      setSavedFolder(null);
      setSteps(draft.steps.filter((s) => find(s.op)).map((s) => ({ uid: uid(), op: s.op, params: { ...defaults(find(s.op)!.params), ...s.params } })));
      setSaved(null);
      setSelected(START);
      setPositions({});
      setUndo([]);
      setRedo([]);
      setTimeout(() => canvas.current?.fit(), 50);
      toast(kind === "ai" ? "Draft from the AI assistant — review each step, choose the input files, then run or save."
        : "Workflow from an earlier run — choose the input files and run it, or save it to keep it in a folder.");
    } catch {
      /* ignore a damaged draft */
    }
  }, [params, meta, find, toast]);

  // Which file types the chosen inputs contain (drives what the first step may be).
  useEffect(() => {
    if (!inputs.length) return setStartExts(null);
    api<{ files: number; extensions: Record<string, number> }>("POST", "/api/fs/scan", { paths: inputs })
      .then((scan) => setStartExts(Object.keys(scan.extensions).length ? Object.keys(scan.extensions) : null))
      .catch(() => setStartExts(null));
  }, [inputs]);

  // ---- editing with undo -------------------------------------------------------
  const snapshot = (): Snapshot => ({ name, steps: steps.map((s) => ({ ...s, params: { ...s.params } })) });
  const change = (next: StepState[], select?: string) => {
    setUndo((u) => [...u.slice(-59), snapshot()]);
    setRedo([]);
    setSteps(next);
    setRunUids([]);
    if (select) setSelected(select);
    editing.current = "";
  };
  const restore = (s: Snapshot) => {
    setName(s.name);
    setSteps(s.steps);
    if (selected !== START && !s.steps.some((x) => x.uid === selected)) setSelected(START);
    editing.current = "";
  };
  const doUndo = () => { const prev = undo[undo.length - 1]; if (!prev) return; setRedo((r) => [...r, snapshot()]); setUndo((u) => u.slice(0, -1)); restore(prev); };
  const doRedo = () => { const next = redo[redo.length - 1]; if (!next) return; setUndo((u) => [...u, snapshot()]); setRedo((r) => r.slice(0, -1)); restore(next); };

  const addAt = (op: Operation, index: number) => {
    const step = { uid: uid(), op: op.id, params: defaults(op.params) };
    const next = [...steps];
    next.splice(index, 0, step);
    change(next, step.uid);
    setMenu(null);
  };
  const opsWith = (list: StepState[]) => list.map((s) => find(s.op)!).filter(Boolean);
  const moveCheck = (i: number, delta: number): string => {
    const j = i + delta;
    if (j < 0 || j >= steps.length) return delta < 0 ? "Already the first step" : "Already the last step";
    const next = [...steps];
    [next[i], next[j]] = [next[j], next[i]];
    return chainValid(opsWith(next), startExts) ? "" : "Moving it would put a step after one whose files it cannot read";
  };
  const removeCheck = (i: number): string => {
    const next = steps.filter((_, k) => k !== i);
    return chainValid(opsWith(next), startExts) ? "" : `The next step cannot read the files of the step before this one`;
  };
  const move = (i: number, delta: number) => {
    if (moveCheck(i, delta)) return;
    const next = [...steps];
    [next[i], next[i + delta]] = [next[i + delta], next[i]];
    setPositions({});
    change(next, next[i + delta].uid);
  };
  const remove = (i: number) => {
    if (removeCheck(i)) return;
    const next = steps.filter((_, k) => k !== i);
    change(next, next[Math.min(i, next.length - 1)]?.uid ?? START);
  };
  const editParams = (index: number, values: Record<string, unknown>) => {
    if (editing.current !== steps[index].uid) {
      setUndo((u) => [...u.slice(-59), snapshot()]);
      setRedo([]);
      editing.current = steps[index].uid;
    }
    setSteps((list) => list.map((s, k) => (k === index ? { ...s, params: values } : s)));
    setRunUids([]);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest("input, textarea, select");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); e.shiftKey ? doRedo() : doUndo(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
      if (e.key === "Delete" && !typing && selected !== START) remove(steps.findIndex((s) => s.uid === selected));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ---- persistence -----------------------------------------------------------------
  const save = async () => {
    try {
      const def = definition();
      if (!def.name) throw new Error("Give the workflow a name (top left) before saving it.");
      await api("PUT", "/api/workflows", { ...def, folder });
      setSaved(JSON.stringify(def));
      setSavedFolder(folder.trim());
      reloadList();
      toast(`Workflow “${def.name}” saved${folder.trim() ? ` in ${folder.trim()}` : ""}.`);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  };
  const newWorkflow = () => {
    setName(""); setFolder(""); setSavedFolder(null); setSteps([]); setSaved(null); setSelected(START); setPositions({}); setUndo([]); setRedo([]); setRunUids([]);
    router.replace("/workflow/");
  };
  const deleteSaved = async () => {
    if (!saved || !window.confirm(`Delete the saved workflow “${name}”?`)) return;
    await api("DELETE", `/api/workflows/${encodeURIComponent(name)}`);
    reloadList();
    newWorkflow();
  };

  // ---- run ------------------------------------------------------------------------------
  const run = () => {
    setSelected(START);
    if (!steps.length) return setError("Add at least one step.");
    if (!inputs.length) return setError("Add the files or folders for the first step.");
    if (steps.some((s) => s.params.move) && !window.confirm("A step is set to move files: originals will be removed from their folders. Continue?")) return;
    setRunUids(steps.map((s) => s.uid));
    start({ mode: "workflow", workflow: { ...definition(), name: name.trim() || "Unsaved workflow" }, inputs, output_dir: outputDir, recursive, keep_intermediate: keepIntermediate }, name.trim() || "Workflow");
  };

  const statusOf = (stepUid: string, index: number) => {
    if (!job || !runUids.length || runUids.join() !== steps.map((s) => s.uid).join()) return undefined;
    let key = "pending";
    if (job.state === "running") key = job.steps[String(index)] ?? "pending";
    else if (job.result?.steps) {
      const s = job.result.steps[index];
      if (s) {
        key = s.status;
        if (s.status === "success" || s.status === "warning") {
          const [label, tone] = TONES[key];
          return { label: `${label} · ${s.outputs} file${s.outputs === 1 ? "" : "s"}`, tone };
        }
      }
    } else if (job.state === "error") key = "failed";
    const [label, tone] = TONES[key] ?? [key, ""];
    void stepUid;
    return { label, tone };
  };

  // ---- canvas model -------------------------------------------------------------
  const broken = new Set<string>();
  const nodes: FlowNode[] = [{
    key: START, kind: "start", icon: "folder", chip: "Start", chipLime: true, title: "Files & folders",
    subtitle: inputs.length ? `${inputs.length} item(s): ${inputs.map((p) => p.split(/[\\/]/).pop()).slice(0, 3).join(", ")}` : ops[0] ? `Add ${formats(ops[0].input_extensions)} files or folders` : "Choose the files to process",
    outFormats: startExts ? formats(startExts) : ops[0] ? formats(ops[0].input_extensions) : "Your files",
    warning: ops[0] && startExts && !canRead(ops[0], startExts) ? `None of these files can be read by “${ops[0].name}”` : undefined,
  }];
  steps.forEach((step, index) => {
    const op = find(step.op);
    if (!op) return;
    const readable = canRead(op, flowingOut(ops, index - 1, startExts));
    if (!readable) broken.add(step.uid);
    nodes.push({
      key: step.uid, kind: op.category, icon: op.category, title: op.name,
      chip: `Step ${index + 1}${statusOf(step.uid, index) ? "" : ` · ${meta?.categories[op.category]}`}`,
      status: statusOf(step.uid, index), subtitle: summary(op, step.params),
      inFormats: formats(op.input_extensions), outFormats: formats(op.output_extensions),
      warning: readable ? undefined : `Cannot read ${formats(flowingOut(ops, index - 1, startExts) ?? [])}`,
    });
  });

  const selectedIndex = steps.findIndex((s) => s.uid === selected);
  const selectedOp = selectedIndex >= 0 ? find(steps[selectedIndex].op) : undefined;

  if (!meta) return null;
  return (
    <div className="builder">
      <div className="builder-top">
        <button className="btn ghost crumb" onClick={() => router.push("/workflows/")}><Icon name="folder" size={18} />Workflows</button>
        <span className="crumb">/</span>
        <input className="folderinput" list="wf-folders" value={folder} placeholder="Folder" title="Folder of this workflow (use / for sub-folders)"
          onChange={(e) => setFolder(e.target.value)} />
        <datalist id="wf-folders">{[...new Set(savedList.map((w) => w.folder).filter(Boolean))].map((f) => <option key={f} value={f} />)}</datalist>
        <span className="crumb">/</span>
        <span className="flow-tile kind-start small"><Icon name="workflow" size={16} /></span>
        <input className="titleinput" value={name} placeholder="Untitled workflow" onChange={(e) => setName(e.target.value)} />
        <span className={`tag ${isSaved ? "green" : "draft"}`}>{isSaved ? "Saved" : "Draft"}</span>
        <div className="grow" />
        <select className="select" style={{ width: 220 }} value="" onChange={(e) => e.target.value && load(e.target.value)}>
          <option value="">Open a saved workflow…</option>
          {[...new Set(savedList.map((w) => w.folder))].sort().map((f) => (
            <optgroup key={f || "-"} label={f || "Not in a folder"}>
              {savedList.filter((w) => w.folder === f).map((w) => <option key={w.name} value={w.name}>{w.name} ({w.steps.length} steps)</option>)}
            </optgroup>
          ))}
        </select>
        <button className="btn pink" onClick={() => router.push("/assistant/?mode=workflow")} title="Describe a workflow and let the AI build it">
          <Icon name="sparkle" size={17} />Ask AI</button>
        <button className="btn" onClick={newWorkflow}><Icon name="plus" size={17} />New</button>
        <button className="btn danger" disabled={!saved} onClick={deleteSaved}><Icon name="trash" size={16} />Delete</button>
        <button className="btn" onClick={save}><Icon name="save" size={17} />Save</button>
        <button className="btn primary" onClick={run} disabled={job?.state === "running"}><Icon name="play" size={16} />Run</button>
      </div>
      <div className="builder-body">
        <FlowCanvas handle={canvas} nodes={nodes} selected={selected} broken={broken} positions={positions} onPositions={setPositions}
          onSelect={(key) => key && setSelected(key)} canUndo={undo.length > 0} canRedo={redo.length > 0} onUndo={doUndo} onRedo={doRedo}
          onAdd={(at) => setMenu({ at, index: steps.length })} onInsert={(after, at) => setMenu({ at, index: after })} />
        <aside className="card inspector">
          <AnimatePresence mode="wait">
            {selectedOp && selectedIndex >= 0 ? (
              <motion.div key={steps[selectedIndex].uid} className="col" style={{ gap: 12 }} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                <div className="row">
                  <span className={`flow-tile kind-${selectedOp.category}`}><Icon name={selectedOp.category} size={24} /></span>
                  <div className="grow">
                    <div className="caption">Step {selectedIndex + 1} · {meta.categories[selectedOp.category]}</div>
                    <div className="h2">{selectedOp.name}</div>
                  </div>
                </div>
                <div className="fmt">Reads <b>{formats(selectedOp.input_extensions)}</b><Icon name="forward" size={14} />Writes <b>{formats(selectedOp.output_extensions)}</b></div>
                <div className="muted" style={{ fontSize: 13 }}>{selectedOp.description}</div>
                <div className="row">
                  {([-1, 1] as const).map((delta) => {
                    const reason = moveCheck(selectedIndex, delta);
                    return <button key={delta} className="btn icon" disabled={!!reason} title={reason || (delta < 0 ? "Move earlier" : "Move later")}
                      onClick={() => move(selectedIndex, delta)}><Icon name={delta < 0 ? "back" : "forward"} size={17} /></button>;
                  })}
                  <div className="grow" />
                  <button className="btn danger" disabled={!!removeCheck(selectedIndex)} title={removeCheck(selectedIndex) || "Remove this step"}
                    onClick={() => remove(selectedIndex)}><Icon name="trash" size={16} />Remove</button>
                </div>
                {removeCheck(selectedIndex) && <div className="help">Can’t remove: {removeCheck(selectedIndex).toLowerCase()}.</div>}
                <div className="caption" style={{ marginTop: 6 }}>Settings</div>
                <ParamForm params={selectedOp.params} values={steps[selectedIndex].params} onChange={(v) => editParams(selectedIndex, v)} />
              </motion.div>
            ) : (
              <motion.div key="start" className="col" style={{ gap: 14 }} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                <div className="row">
                  <span className="flow-tile kind-start"><Icon name="folder" size={24} /></span>
                  <div><div className="caption">Start</div><div className="h2">Files & folders</div></div>
                </div>
                <div className="muted" style={{ fontSize: 13 }}>These files go into the first step. Each following step receives the files produced by the step before it.</div>
                <InputList title="Input" extensions={ops[0]?.input_extensions ?? []} value={inputs} onChange={setInputs} />
                <RunPanel outputDir={outputDir} onOutputDir={setOutputDir} recursive={recursive} onRecursive={setRecursive}
                  onRun={run} onCancel={cancel} job={job} error={error} runLabel="Run workflow"
                  keepIntermediate={keepIntermediate} onKeepIntermediate={setKeepIntermediate} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </div>
      {menu && (
        <AddStepMenu operations={meta.operations} categories={meta.categories} position={{
          x: Math.min(menu.at.x, window.innerWidth - 470), y: Math.max(12, Math.min(menu.at.y, window.innerHeight - 470)) }}
          reads={flowingOut(ops, menu.index - 1, startExts)} feeds={menu.index < ops.length ? ops[menu.index] : null}
          onPick={(op) => addAt(op, menu.index)} onClose={() => setMenu(null)} />
      )}
    </div>
  );
}

export default function Page() {
  return <Suspense><Builder /></Suspense>;
}
