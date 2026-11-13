"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type JobState, watchJob } from "./api";
import { useApp } from "./app-context";

/** Start a background job, follow its progress, and expose its state. */
export function useJob() {
  const { trackJob, toast } = useApp();
  const [job, setJob] = useState<JobState | null>(null);
  const [error, setError] = useState("");
  const stop = useRef<() => void>(undefined);

  useEffect(() => () => stop.current?.(), []);

  const start = useCallback(async (body: Record<string, unknown>, label: string) => {
    setError("");
    setJob(null);
    try {
      const first = await api<JobState>("POST", "/api/jobs", body);
      setJob(first);
      trackJob({ id: first.id, label, state: first });
      stop.current?.();
      stop.current = watchJob(first.id, (state) => {
        setJob(state);
        if (body.mode !== "preview") trackJob({ id: state.id, label, state });
        else if (state.state !== "running") trackJob({ id: state.id, label, state });
      });
    } catch (e) {
      const message = e instanceof ApiError ? e.message : String(e);
      setError(message);
      toast(message, "error");
    }
  }, [trackJob, toast]);

  const cancel = useCallback(async () => {
    if (job) await api("POST", `/api/jobs/${job.id}/cancel`).catch(() => {});
  }, [job]);

  return { job, error, start, cancel, running: job?.state === "running", setError };
}
