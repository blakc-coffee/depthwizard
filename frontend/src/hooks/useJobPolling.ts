import { useEffect, useRef, useState } from 'react';
import { getJob } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { JobStatusResponse } from '../lib/types';

interface UseJobPollingResult {
  jobData: JobStatusResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useJobPolling(
  jobId: string | undefined,
  intervalMs = 2000
): UseJobPollingResult {
  const [jobData, setJobData] = useState<JobStatusResponse | null>(null);
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
      const data = await getJob(id);
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

  return {
    jobData,
    loading,
    error,
    refresh,
  };
}
