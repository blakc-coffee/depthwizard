import { useEffect, useRef, useState } from 'react';
import { getSiltJob } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { SiltJobStatusResponse } from '../lib/types';

// Mirrors useJobPolling.ts's shape — a dedicated hook rather than a
// generic/parametrized one since the two response types (JobStatusResponse
// vs SiltJobStatusResponse) genuinely differ, and this hook is short enough
// that duplicating it is cheaper than the coupling a shared generic version
// would add to the terrain hook's only other consumer.
interface UseSiltJobPollingResult {
  jobData: SiltJobStatusResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useSiltJobPolling(
  jobId: string | undefined,
  intervalMs = 2000
): UseSiltJobPollingResult {
  const [jobData, setJobData] = useState<SiltJobStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const stopPolling = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const fetchJobStatus = async (id: string) => {
    try {
      const data = await getSiltJob(id);
      setJobData(data);
      setError(null);
      setLoading(false);

      if (data.status === 'completed' || data.status === 'failed') {
        stopPolling();
      }
    } catch (err) {
      const errMsg = getFriendlyErrorMessage(err);
      setError(errMsg);
      setLoading(false);
      stopPolling();
    }
  };

  useEffect(() => {
    if (!jobId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    fetchJobStatus(jobId);

    timerRef.current = setInterval(() => {
      fetchJobStatus(jobId);
    }, intervalMs);

    return () => {
      stopPolling();
    };
  }, [jobId, intervalMs]);

  const refresh = async () => {
    if (jobId) {
      await fetchJobStatus(jobId);
    }
  };

  return { jobData, loading, error, refresh };
}
