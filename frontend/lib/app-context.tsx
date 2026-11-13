"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, type JobState, type Meta, type Operation, type Settings, type Stats } from "./api";

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

  const value = useMemo<AppValue>(() => ({
    meta, settings, stats, error, op: (id) => meta?.operations.find((o) => o.id === id),
    saveSettings, refreshStats, refreshMeta, toast, activeJobs, trackJob, railCollapsed, setRailCollapsed,
  }), [meta, settings, stats, error, saveSettings, refreshStats, refreshMeta, toast, activeJobs, trackJob, railCollapsed]);

  return (
    <AppContext.Provider value={value}>
      {children}
      {toastState && <div className={`toast ${toastState.kind === "error" ? "error" : ""}`}>{toastState.message}</div>}
    </AppContext.Provider>
  );
}
