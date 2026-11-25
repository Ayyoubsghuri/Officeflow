"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, reportError, watchJob, type JobState, type Meta, type Operation, type Settings, type Stats } from "./api";

/** The AI assistant's latest request. It lives here, not on the Assistant page, so it keeps
 *  running when you go to another page and its answer is waiting when you come back. */
export interface AiJob {
  id: string;
  mode: "workflow" | "plugin";
  request: string;
  state: JobState | null;
  seen: boolean;             // the answer (or error) has been shown on the Assistant page
}

const AI_JOB_KEY = "officeflow-ai-job";
export const AI_LAST_KEY = "officeflow-ai-last";

export function readStored<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function writeStored(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the Activity list still keeps every answer */
  }
}

export interface ActiveJob {
  id: string;
  label: string;
  state: JobState | null;
}

interface AppValue {
  meta: Meta | null;
  settings: Settings | null;
  stats: Stats | null;
  error: string;
  op(id: string): Operation | undefined;
  saveSettings(patch: Partial<Settings>): Promise<void>;
  refreshStats(): Promise<void>;
  refreshMeta(): Promise<void>;
  toast(message: string, kind?: "info" | "error"): void;
  activeJobs: ActiveJob[];
  trackJob(job: ActiveJob): void;
  railCollapsed: boolean;
  setRailCollapsed(value: boolean): void;
  aiJob: AiJob | null;
  startAiJob(mode: AiJob["mode"], request: string): Promise<void>;
  markAiSeen(): void;
}

const AppContext = createContext<AppValue | null>(null);

export function useApp(): AppValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp outside AppProvider");
  return value;
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState("");
  const [toastState, setToastState] = useState<{ message: string; kind: string } | null>(null);
  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([]);
  const [railCollapsed, setRailCollapsed] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const refreshStats = useCallback(async () => {
    try {
      setStats(await api<Stats>("GET", "/api/stats"));
    } catch {
      /* shown elsewhere */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [m, s] = await Promise.all([api<Meta>("GET", "/api/meta"), api<Settings>("GET", "/api/settings")]);
        setMeta(m);
        setSettings(s);
        await refreshStats();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [refreshStats]);

  // Errors outside React rendering (events, promises) go to the log and a message.
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      reportError(event.message, event.error?.stack ?? "");
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      reportError(reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason),
        reason instanceof Error ? reason.stack ?? "" : "");
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = settings?.theme ?? "dark";
  }, [settings?.theme]);

  const toast = useCallback((message: string, kind: "info" | "error" = "info") => {
    setToastState({ message, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastState(null), 4200);
  }, []);

  const refreshMeta = useCallback(async () => {
    try {
      setMeta(await api<Meta>("GET", "/api/meta"));
    } catch {
      /* keep the previous list */
    }
  }, []);

  const saveSettings = useCallback(async (patch: Partial<Settings>) => {
    setSettings((current) => (current ? { ...current, ...patch } : current));
    try {
      setSettings(await api<Settings>("PUT", "/api/settings", patch));
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    }
  }, [toast]);

  const trackJob = useCallback((job: ActiveJob) => {
    setActiveJobs((jobs) => {
      const others = jobs.filter((j) => j.id !== job.id);
      const finished = job.state && job.state.state !== "running";
      return finished ? others : [...others, job];
    });
    if (job.state && job.state.state !== "running") refreshStats();
  }, [refreshStats]);

  // ---- AI assistant job: survives page changes (and app restarts, through local storage) ----
  const [aiJob, setAiJobState] = useState<AiJob | null>(null);
  const aiStop = useRef<() => void>(undefined);
  const setAiJob = useCallback((update: (job: AiJob | null) => AiJob | null) => {
    setAiJobState((current) => {
      const next = update(current);
      writeStored(AI_JOB_KEY, next);
      return next;
    });
  }, []);

  const followAiJob = useCallback((id: string, mode: AiJob["mode"], request: string) => {
    const label = aiLabel(mode);
    aiStop.current?.();
    const onUpdate = (state: JobState) => {
      trackJob({ id, label, state });
      setAiJob((job) => (job && job.id === id ? { ...job, state } : job));
      if (state.state === "running") return;
      const onAssistant = window.location.pathname.startsWith("/assistant");
      if (state.state === "done" && state.result) {
        writeStored(AI_LAST_KEY, { answer: state.result, request });
      }
      if (!onAssistant) {
        toast(state.state === "done" ? "The AI assistant has finished — open AI Assistant to see what it made."
          : "The AI assistant could not finish — open AI Assistant to see why.", state.state === "done" ? "info" : "error");
      }
    };
    // A job the server no longer knows (OfficeFlow was closed while it worked) ends with a clear message.
    api<JobState>("GET", `/api/jobs/${id}`).then((state) => {
      onUpdate(state);
      if (state.state === "running") aiStop.current = watchJob(id, onUpdate);
    }).catch(() => {
      setAiJob((job) => job && job.id === id ? { ...job, state: {
        id, kind: "ai", state: "error", progress: { done: 0, total: 0, message: "" }, steps: {}, result: null, output_dir: "", elapsed: 0,
        error: "OfficeFlow was closed before the AI finished. Send the request again — anything it did finish is listed under Activity.",
      } } : job);
    });
  }, [setAiJob, toast, trackJob]);

  useEffect(() => {
    const stored = readStored<AiJob>(AI_JOB_KEY);
    if (!stored) return;
    setAiJobState(stored);
    if (!stored.state || stored.state.state === "running") followAiJob(stored.id, stored.mode, stored.request);
    return () => aiStop.current?.();
  }, [followAiJob]);

  const startAiJob = useCallback(async (mode: AiJob["mode"], request: string) => {
    const first = await api<JobState>("POST", "/api/ai/jobs", { kind: mode, request });
    setAiJob(() => ({ id: first.id, mode, request, state: first, seen: false }));
    trackJob({ id: first.id, label: aiLabel(mode), state: first });
    followAiJob(first.id, mode, request);
  }, [followAiJob, setAiJob, trackJob]);

  const markAiSeen = useCallback(() => {
    setAiJob((job) => (job && !job.seen && job.state && job.state.state !== "running" ? { ...job, seen: true } : job));
  }, [setAiJob]);

  const value = useMemo<AppValue>(() => ({
    meta, settings, stats, error, op: (id) => meta?.operations.find((o) => o.id === id),
    saveSettings, refreshStats, refreshMeta, toast, activeJobs, trackJob, railCollapsed, setRailCollapsed,
    aiJob, startAiJob, markAiSeen,
  }), [meta, settings, stats, error, saveSettings, refreshStats, refreshMeta, toast, activeJobs, trackJob, railCollapsed,
    aiJob, startAiJob, markAiSeen]);

  return (
    <AppContext.Provider value={value}>
      {children}
      {toastState && <div className={`toast ${toastState.kind === "error" ? "error" : ""}`}>{toastState.message}</div>}
    </AppContext.Provider>
  );
}

function aiLabel(mode: AiJob["mode"]): string {
  return mode === "workflow" ? "AI · designing a workflow" : "AI · writing a tool";
}
