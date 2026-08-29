/**
 * Polling loop for one job (PRD §10.3).
 *
 * 2 s interval, backing off to 5 s after 60 s. Cleans up on unmount.
 * Fetches the result automatically once status === "completed".
 */

import { useEffect, useRef, useState } from "react";
import { getJob, getJobResult, DepthWizardError } from "../lib/api";
import type { JobStatus, JobStage, JobResult, ApiError } from "../lib/types";

const FAST_MS = 2_000;
const SLOW_MS = 5_000;
const BACKOFF_AFTER_MS = 60_000;

export function useJobPolling(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | "idle">("idle");
  const [stage, setStage] = useState<JobStage | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const startedAt = useRef<number>(0);

  useEffect(() => {
    if (!jobId) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    startedAt.current = Date.now();

    const tick = async () => {
      try {
        const s = await getJob(jobId);
        if (cancelled) return;

        setStatus(s.status);
        setStage(s.stage);
        setProgress(s.progress);

        if (s.status === "failed") {
          setError(s.error ?? { code: "INTERNAL_ERROR", message: "Processing failed." });
          return;                                  // stop polling
        }

        if (s.status === "completed") {
          const r = await getJobResult(jobId);
          if (!cancelled) setResult(r);
          return;                                  // stop polling
        }

        const elapsed = Date.now() - startedAt.current;
        timer = setTimeout(tick, elapsed > BACKOFF_AFTER_MS ? SLOW_MS : FAST_MS);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof DepthWizardError
            ? { code: e.code, message: e.message }
            : { code: "INTERNAL_ERROR", message: "Network error." },
        );
      }
    };

    void tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [jobId]);

  return { status, stage, progress, result, error };
}
