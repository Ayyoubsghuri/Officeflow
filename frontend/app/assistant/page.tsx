"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { Check } from "@/components/ParamForm";
import { api, type AiActivity, type AiAnswer, type AiPreview, type AiStatus, type Operation } from "@/lib/api";
import { useApp } from "@/lib/app-context";
import { formats } from "@/lib/formats";
import { useJob } from "@/lib/useJob";

type Mode = "workflow" | "plugin";

const EXAMPLES: Record<Mode, string[]> = {
  workflow: [
    "Sort scanned invoices from several folders into one folder per reference like 2024/01/005, then list every reference in Excel.",
    "Merge all the Excel files of a folder, clean them, remove duplicate clients by email and make a formatted report by city.",
    "From an Excel list of employees, generate one Word certificate per person from my template and convert them to PDF.",
  ],
  plugin: [
    "A PDF tool that adds the text “CONFIDENTIAL” as a diagonal watermark on every page.",
    "An Excel tool that splits a full-name column into first name and last name columns.",
    "A PDF tool that lists, in Excel, the number of pages and the title of each PDF.",
  ],
};

function modelLabel(status: AiStatus, model: string): string {
  return status.models[model]?.split(" —")[0] ?? model;
}

function Privacy({ status, redact, onRedact }: { status: AiStatus | null; redact: boolean; onRedact(v: boolean): void }) {
  return (
    <div className="card pad col privacy">
      <div className="row"><Icon name="shield" size={22} /><div className="h2">Your data stays on this computer</div></div>
      <div className="privacy-cols">
        <div>
          <div className="caption">Never sent</div>
          <ul className="privacy-list keep">
            <li>Your files and their contents</li>
            <li>File names and folder paths</li>
            <li>Results, history and logs</li>
            <li>Your API key (stored encrypted, only used to sign requests)</li>
          </ul>
        </div>
        <div>
          <div className="caption">Sent to {status?.provider_label ?? "the AI"}</div>
          <ul className="privacy-list send">
            <li>Your request text — you review it before it leaves</li>
            <li>OfficeFlow’s tool list: names, settings, file formats</li>
          </ul>
        </div>
      </div>
      <Check on={redact} onChange={onRedact} label="Hide file paths and e-mail addresses in my requests automatically" />
      {status?.provider === "openai" && <div className="help">OpenAI requests are sent with storage turned off (store=false).</div>}
      <div className="help">The AI only designs workflows and writes tools. Nothing it returns runs by itself: workflows open as drafts, and tools are installed only after you read the code and approve.</div>
    </div>
  );
}

function WorkflowResult({ answer, ops, onOpen, onCreateTool }: {
  answer: AiAnswer; ops: (id: string) => Operation | undefined; onOpen(): void; onCreateTool(text: string): void;
}) {
  const steps = answer.workflow?.steps ?? [];
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row">
        <div className="grow">
          <div className="caption">Proposed workflow</div>
          <div className="h2">{answer.name}</div>
        </div>
        {steps.length > 0 && <button className="btn primary" onClick={onOpen}><Icon name="workflow" size={17} />Open in Workflow Builder</button>}
      </div>
      <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{answer.explanation}</div>
      <div className="col" style={{ gap: 8 }}>
        {steps.map((step, i) => {
          const op = ops(step.op);
          const shown = Object.entries(step.params).filter(([, v]) => v !== "" && v !== null).slice(0, 3);
          return (
            <motion.div key={i} className="ai-step" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}>
              <span className={`flow-tile small kind-${op?.category}`}><Icon name={op?.category ?? "file"} size={16} /></span>
              <div className="grow">
                <div className="row" style={{ gap: 8 }}><b>{i + 1}. {op?.name ?? step.op}</b>
                  {op && <span className="fmt"><b>{formats(op.input_extensions)}</b>→<b>{formats(op.output_extensions)}</b></span>}</div>
                {shown.length > 0 && <div className="faint ellipsis" style={{ fontSize: 12 }}>{shown.map(([k, v]) => `${k}: ${String(v).split("\n")[0]}`).join(" · ")}</div>}
              </div>
            </motion.div>
          );
        })}
      </div>
      {(answer.notes ?? []).length > 0 && <div className="banner warning"><b>Before running</b><ul>{answer.notes!.map((n) => <li key={n}>{n}</li>)}</ul></div>}
      {(answer.missing_tools ?? []).map((tool) => (
        <div key={tool.name} className="banner">
          <div className="row">
            <div className="grow"><b>Missing tool: {tool.name}</b><div className="muted" style={{ fontSize: 13 }}>{tool.description} ({formats(tool.reads)} → {formats(tool.writes)})</div></div>
            <button className="btn pink" onClick={() => onCreateTool(`${tool.name}: ${tool.description} It reads ${tool.reads.join(", ")} files and writes ${tool.writes.join(", ")} files.`)}>
              <Icon name="sparkle" size={16} />Create this tool</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function PluginResult({ answer, onInstalled }: { answer: AiAnswer; onInstalled(ids: string[]): void }) {
  const { toast } = useApp();
  const [approved, setApproved] = useState(false);
  const [installing, setInstalling] = useState(false);
  const check = answer.check!;
  const install = async (replace = false) => {
    setInstalling(true);
    try {
      const done = await api<{ file: string; tools: string[] }>("POST", "/api/plugins", { file_name: answer.file_name, code: answer.code, replace });
      toast(`Installed ${done.file}`);
      onInstalled(done.tools);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (message.includes("already exists") && window.confirm(`${message}\nReplace it with this version?`)) return install(true);
      toast(message, "error");
    } finally {
      setInstalling(false);
    }
  };
  return (
    <div className="col" style={{ gap: 14 }}>
      <div><div className="caption">Proposed plugin · {answer.file_name}</div>
        <div className="h2">{check.tools.map((t) => t.name).join(", ")}</div></div>
      <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{answer.explanation}</div>
      <div className={`banner ${check.ok ? "success" : "failed"}`}>
        <div className="row"><Icon name="shield" size={18} /><b>{check.ok ? "Safety check passed" : "Safety check failed"}</b></div>
        <ul>
          <li>Uses only offline libraries — no network access, no launching programs, no hidden code.</li>
          <li>Adds: {check.tools.map((t) => `${t.name} (${t.id})`).join(", ")}</li>
          {check.warnings.map((w) => <li key={w} style={{ color: "var(--warning)" }}>{w}</li>)}
          {check.errors.map((e) => <li key={e}>{e}</li>)}
        </ul>
      </div>
      <div className="codeview selectable">
        {(answer.code ?? "").split("\n").map((line, i) => (
          <div key={i} className="codeline"><span className="ln">{i + 1}</span><span>{line || " "}</span></div>
        ))}
      </div>
      <Check on={approved} onChange={setApproved} label="I have read this code and want to install it as a plugin on this computer" />
      <div><button className="btn primary" disabled={!approved || !check.ok || installing} onClick={() => install()}>
        <Icon name="plus" size={17} />{installing ? "Installing…" : "Install plugin"}</button></div>
    </div>
  );
}

function Assistant() {
  const { op, refreshMeta, saveSettings, settings, toast } = useApp();
  const router = useRouter();
  const params = useSearchParams();
  const [status, setStatus] = useState<AiStatus | null>(null);
  const [mode, setMode] = useState<Mode>((params.get("mode") as Mode) || "workflow");
  const [request, setRequest] = useState(params.get("q") ?? "");
  const [preview, setPreview] = useState<AiPreview | null>(null);
  const [activity, setActivity] = useState<AiActivity[]>([]);
  const [installed, setInstalled] = useState<string[]>([]);
  const { job, error, start } = useJob();

  const loadActivity = useCallback(() => api<AiActivity[]>("GET", "/api/ai/activity").then(setActivity).catch(() => {}), []);
  useEffect(() => {
    api<AiStatus>("GET", "/api/ai/status").then(setStatus).catch(() => {});
    loadActivity();
  }, [loadActivity]);
  useEffect(() => { if (job && job.state !== "running") loadActivity(); }, [job, loadActivity]);

  const review = async () => {
    if (!request.trim()) return toast("Describe what you want first.", "error");
    setPreview(await api<AiPreview>("POST", "/api/ai/preview", { kind: mode, request }));
  };
  const send = () => {
    setInstalled([]);
    start({ kind: mode, request }, mode === "workflow" ? "AI · designing a workflow" : "AI · writing a tool", "/api/ai/jobs");
    setPreview(null);
  };
  const answer = job?.state === "done" ? (job.result as unknown as AiAnswer) : null;
  const running = job?.state === "running";

  return (
    <div className="col" style={{ gap: 18 }}>
      <div className="row">
        <div className="grow">
          <h1 className="h1">AI Assistant</h1>
          <div className="muted" style={{ marginTop: 6 }}>Describe what you need. The AI designs a workflow or writes a new tool — your documents never leave this computer.</div>
        </div>
        {status && (status.configured ? (
          <span className="pill" style={{ height: 40 }}><span className="dot-ok" />Connected · {status.provider_label} · {modelLabel(status, status.model)} · key {status.key_hint}</span>
        ) : (
          <Link className="btn primary" href="/settings/#ai"><Icon name="key" size={17} />Connect {status.provider_label}</Link>
        ))}
      </div>

      <div className="assistant">
        <div className="col" style={{ gap: 18, minWidth: 0 }}>
          <div className="card pad col" style={{ gap: 14 }}>
            <div className="segmented">
              {(["workflow", "plugin"] as Mode[]).map((m) => (
                <button key={m} className={mode === m ? "on" : ""} onClick={() => { setMode(m); setPreview(null); }}>
                  <Icon name={m === "workflow" ? "workflow" : "code"} size={17} />{m === "workflow" ? "Create a workflow" : "Create a tool (plugin)"}
                  {mode === m && <motion.span layoutId="seg" className="seg-bg" />}
                </button>
              ))}
            </div>
            <textarea className="textarea prompt" value={request} onChange={(e) => { setRequest(e.target.value); setPreview(null); }}
              placeholder={mode === "workflow" ? "What should the workflow do? Mention the kind of files and what you want at the end." : "What should the new tool do? Mention what it reads and what it should produce."} />
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              {EXAMPLES[mode].map((example) => (
                <button key={example} className="example" onClick={() => { setRequest(example); setPreview(null); }}>{example}</button>
              ))}
            </div>
            <div className="row">
              <button className="btn primary" disabled={!status?.configured || running} onClick={review}><Icon name="eye" size={17} />Review before sending</button>
              {!status?.configured && <span className="muted" style={{ fontSize: 13 }}>Add an API key in Settings first.</span>}
            </div>
            <AnimatePresence>
              {preview && (
                <motion.div className="sendbox" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <div className="caption">Exactly this text will be sent{preview.replaced.length ? " (hidden parts replaced)" : ""}</div>
                  <pre className="selectable">{preview.sent}</pre>
                  {preview.replaced.length > 0 && (
                    <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                      {preview.replaced.map((r) => <span key={r.placeholder} className="tag" title={r.original}>{r.placeholder} = {r.kind} kept on this computer</span>)}
                    </div>
                  )}
                  <div className="help">Also sent: the list of OfficeFlow’s {preview.catalog_tools} tools{mode === "plugin" ? " and the plugin rules" : ""}. Nothing else.</div>
                  <div className="row">
                    <button className="btn primary" onClick={send}><Icon name="send" size={16} />Send to {status ? modelLabel(status, preview.model) : "AI"}</button>
                    <button className="btn ghost" onClick={() => setPreview(null)}>Edit</button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {(running || answer || error || job?.state === "error") && (
            <div className="card pad">
              {running && <div className="row"><span className="spin dark" /><span>{mode === "workflow" ? "Designing your workflow…" : "Writing your tool and checking it…"} {job?.elapsed ? `${Math.round(job.elapsed)} s` : ""}</span></div>}
              {(error || job?.state === "error") && <div className="banner failed"><b>Could not complete</b><div>{error || job?.error}</div></div>}
              {answer?.kind === "workflow" && (
                <WorkflowResult answer={answer} ops={op}
                  onOpen={() => {
                    sessionStorage.setItem("officeflow-ai-draft", JSON.stringify(answer.workflow));
                    router.push("/workflow/?draft=ai");
                  }}
                  onCreateTool={(text) => { setMode("plugin"); setRequest(text); window.scrollTo(0, 0); }} />
              )}
              {answer?.kind === "plugin" && !installed.length && (
                <PluginResult answer={answer} onInstalled={(ids) => { setInstalled(ids); refreshMeta(); }} />
              )}
              {installed.length > 0 && (
                <div className="banner success">
                  <b>Plugin installed.</b> It is now in its toolbox and in the Workflow Builder.
                  <div className="row" style={{ marginTop: 10 }}>
                    {installed.map((id) => <button key={id} className="btn" onClick={() => router.push(`/tool/?id=${id}`)}><Icon name="arrow" size={16} />Open {op(id)?.name ?? id}</button>)}
                  </div>
                </div>
              )}
              {answer && <div className="faint" style={{ fontSize: 12, marginTop: 12 }}>{answer.usage.input_tokens + answer.usage.output_tokens} tokens · {answer.rounds} round{answer.rounds > 1 ? "s" : ""} (OfficeFlow checks every answer and asks for fixes automatically)</div>}
            </div>
          )}
        </div>

        <div className="col" style={{ gap: 18 }}>
          <Privacy status={status} redact={settings?.ai_redact ?? true} onRedact={(v) => saveSettings({ ai_redact: v })} />
          <div className="card pad col" style={{ gap: 10 }}>
            <div className="h2">Activity</div>
            <div className="help" style={{ marginTop: 0 }}>Kept on this computer: exactly what was sent each time.</div>
            {activity.length === 0 && <div className="muted">Nothing sent yet.</div>}
            {activity.slice(0, 8).map((entry, i) => (
              <details key={i} className="activity">
                <summary><span className="tag">{entry.kind}</span> <span className="ellipsis">{entry.outcome}</span></summary>
                <div className="faint" style={{ fontSize: 12 }}>{new Date(entry.time).toLocaleString()} · {entry.model}</div>
                <pre className="selectable">{entry.sent_request}</pre>
              </details>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><Assistant /></Suspense>;
}
