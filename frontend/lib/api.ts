// Client for the local OfficeFlow API (served by the Python process).

export type ParamType = "text" | "multiline" | "int" | "bool" | "choice" | "file";

export interface Param {
  key: string;
  label: string;
  type: ParamType;
  default: unknown;
  help: string;
  choices: [string, string][];
  required: boolean;
  minimum: number;
  maximum: number;
  placeholder: string;
  extensions: string[];
}

export interface Operation {
  id: string;
  name: string;
  category: string;
  description: string;
  input_label: string;
  input_extensions: string[];
  output_extensions: string[];
  min_inputs: number;
  max_inputs: number | null;
  params: Param[];
}

export interface Meta {
  version: string;
  platform: string;
  categories: Record<string, string>;
  operations: Operation[];
  pdf_converter: string | null;
  plugin_problems: string[];
  home: string;
  desktop: boolean;
}

export interface Settings {
  theme: "dark" | "light";
  output_dir: string;
  include_subfolders: boolean;
  last_input_dir: string;
  ai_model: string;
  ai_redact: boolean;
  ai_provider: AiProvider;
  ai_openai_model: string;
  ai_openrouter_model: string;
  ai_nvidia_model: string;
}

export type AiProvider = "anthropic" | "openai" | "openrouter" | "nvidia";

export interface AiStatus {
  provider: AiProvider;
  provider_label: string;
  configured: boolean;
  key_hint: string;
  sdk: boolean;
  model: string;
  models: Record<string, string>;       // Claude models
  openai_model: string;
  providers: Record<AiProvider, { label: string; configured: boolean; key_hint: string; sdk: boolean; model: string; default_model: string }>;
  redact: boolean;
}

export interface AiPreview {
  sent: string;
  replaced: { kind: string; original: string; placeholder: string }[];
  catalog_tools: number;
  model: string;
  provider: AiProvider;
  provider_label: string;
}

export interface PluginCheck {
  ok: boolean;
  errors: string[];
  warnings: string[];
  tools: { id: string; name: string; category: string; class: string }[];
}

export interface AiAnswer {
  kind: "workflow" | "plugin";
  sent: string;
  explanation: string;
  rounds: number;
  usage: { input_tokens: number; output_tokens: number };
  // workflow
  name?: string;
  workflow?: WorkflowDef;
  notes?: string[];
  missing_tools?: { name: string; description: string; reads: string[]; writes: string[] }[];
  // plugin
  file_name?: string;
  code?: string;
  check?: PluginCheck;
}

export interface AiActivity {
  time: string;
  kind: string;
  model: string;
  sent_request: string;
  also_sent: string;
  outcome: string;
  usage: { input_tokens?: number; output_tokens?: number };
  answer?: Partial<AiAnswer> | null;
}

export interface PluginFile {
  file: string;
  tools: { id: string; name: string }[];
  loaded: boolean;
  size: number;
}

export interface Run {
  id: number;
  kind: "operation" | "workflow";
  target_id: string;
  name: string;
  started_at: string;
  duration_s: number;
  status: Status;
  input_count: number;
  output_count: number;
  output_dir: string;
  summary: string;
  details: {
    params?: Record<string, unknown>;
    warnings?: string[];
    errors?: string[];
    steps?: { name: string; status: Status; summary: string; errors: string[]; warnings: string[] }[];
  };
}

export type Status = "success" | "warning" | "failed" | "cancelled" | "info";

export interface TargetStat {
  runs: number;
  ok: number;
  started_at: string;
  summary: string;
  status: Status;
}

export interface Stats {
  runs: number;
  files: number;
  ok: number;
  targets: Record<string, TargetStat>;
}

export interface Result {
  status: Status;
  summary: string;
  headers: string[];
  rows: string[][];
  total_rows: number;
  warnings: string[];
  errors: string[];
  outputs: string[];
  output_count: number;
  reports: string[];
  steps?: { name: string; status: Status; summary: string; outputs: number }[];
  result_dir?: string;
}

export interface JobState {
  id: string;
  kind: "preview" | "run" | "workflow" | "ai";
  state: "running" | "done" | "error";
  progress: { done: number; total: number; message: string };
  steps: Record<string, string>;
  result: (Result & Partial<AiAnswer>) | null;
  error: string;
  output_dir: string;
  elapsed: number;
}

export interface WorkflowStep {
  op: string;
  params: Record<string, unknown>;
  keep?: boolean;               // also save this step's files in the result folder
}

export interface WorkflowDef {
  name: string;
  steps: WorkflowStep[];
  folder?: string;
}

export interface FolderListing {
  path: string;
  parent: string | null;
  entries: { name: string; path: string; dir: boolean; size: number; ext: string }[];
  roots: { name: string; path: string }[];
}

export class ApiError extends Error {}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

function token(): string {
  if (typeof window === "undefined") return "";
  const fromUrl = new URLSearchParams(window.location.search).get("token");
  if (fromUrl) {
    sessionStorage.setItem("officeflow-token", fromUrl);
    return fromUrl;
  }
  return sessionStorage.getItem("officeflow-token") ?? process.env.NEXT_PUBLIC_API_TOKEN ?? "";
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json", "X-OfficeFlow-Token": token() },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("OfficeFlow's engine is not responding. Restart the application.");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail);
  }
  return (await response.json()) as T;
}

/** Follow a job until it ends. Uses a server-sent event stream, with polling as a fallback. */
export function watchJob(id: string, onUpdate: (job: JobState) => void): () => void {
  let closed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const poll = async () => {
    if (closed) return;
    try {
      const job = await api<JobState>("GET", `/api/jobs/${id}`);
      onUpdate(job);
      if (job.state === "running") timer = setTimeout(poll, 300);
    } catch {
      timer = setTimeout(poll, 1000);
    }
  };
  let source: EventSource | undefined;
  if (typeof EventSource !== "undefined") {
    source = new EventSource(`${BASE}/api/jobs/${id}/events?token=${encodeURIComponent(token())}`);
    source.onmessage = (event) => {
      const job = JSON.parse(event.data) as JobState;
      onUpdate(job);
      if (job.state !== "running") source?.close();
    };
    source.onerror = () => {
      source?.close();
      poll();
    };
  } else {
    poll();
  }
  return () => {
    closed = true;
    source?.close();
    if (timer) clearTimeout(timer);
  };
}

/** Send an interface error to the engine's log (best effort, never throws). */
export function reportError(message: string, stack = ""): void {
  if (typeof window === "undefined") return;
  api("POST", "/api/client-error", { message, stack, page: window.location.pathname + window.location.search }).catch(() => {});
}

export interface LibraryEntry {
  kind: "saved" | "run" | "ai";
  key: string;
  name: string;
  folder: string;
  steps: string[];
  definition?: WorkflowDef;
  runs: number;
  ok: number;
  last_run: string;
  last_status: string;
  last_summary: string;
  updated_at?: string;
  proposed_at?: string;
}

export interface Library {
  saved: LibraryEntry[];
  recent: LibraryEntry[];
  ai: LibraryEntry[];
  folders: string[];
}
