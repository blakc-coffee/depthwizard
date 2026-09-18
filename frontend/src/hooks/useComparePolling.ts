import { useEffect, useRef, useState } from 'react';
import { getCompare } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { CompareStatusResponse } from '../lib/types';

interface UseComparePollingResult {
  compareData: CompareStatusResponse | null;
  loading: boolean;
  error: string | null;
}

// Mirrors useJobPolling exactly — separate hook because it polls a distinct
// resource/endpoint (GET /api/v1/compare/{id}), not because the logic differs.
export function useComparePolling(
  compareId: string | undefined,
  intervalMs = 2000
): UseComparePollingResult {
  const [compareData, setCompareData] = useState<CompareStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const stopPolling = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const fetchCompareStatus = async (id: string) => {
    try {
      const data = await getCompare(id);
      setCompareData(data);
      setError(null);
      setLoading(false);

      if (data.status === 'completed' || data.status === 'failed') {
        stopPolling();
      }
    } catch (err) {
      setError(getFriendlyErrorMessage(err));
      setLoading(false);
      stopPolling();
    }
  };

  useEffect(() => {
    if (!compareId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    fetchCompareStatus(compareId);

    timerRef.current = setInterval(() => {
      fetchCompareStatus(compareId);
    }, intervalMs);

    return () => {
      stopPolling();
    };
  }, [compareId, intervalMs]);

  return { compareData, loading, error };
}
