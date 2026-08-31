import { useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { JobStatus } from '../components/jobs/JobStatus';
import { AppShell } from '../components/layout/AppShell';
import { useJobPolling } from '../hooks/useJobPolling';

export const ProcessingPage = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const { jobData, loading, error, refresh } = useJobPolling(jobId);

  useEffect(() => {
    document.title = 'DepthWizard | Processing Job';
  }, []);

  useEffect(() => {
    if (jobData?.status === 'completed' && jobId) {
      navigate(`/results/${encodeURIComponent(jobId)}`, { replace: true });
    }
  }, [jobData?.status, jobId, navigate]);

  const handleReturnToWorkspace = () => {
    navigate('/app');
  };

  return (
    <AppShell>
      <div className="w-full flex-1">
        {loading && !jobData && !error ? (
          <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-8 max-w-2xl mx-auto shadow-xs text-center my-auto">
            <div className="flex items-center justify-center space-x-3 text-[#36394a] text-sm font-medium">
              <svg
                className="animate-spin h-5 w-5 text-[#5e4cff]"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Connecting to job status service…</span>
            </div>
          </div>
        ) : (
          <JobStatus
            status={jobData?.status || (error ? 'failed' : 'queued')}
            stage={jobData?.stage}
            progress={jobData?.progress}
            error={error || jobData?.error?.message}
            onRetry={refresh}
            onReturnToWorkspace={handleReturnToWorkspace}
          />
        )}
      </div>
    </AppShell>
  );
};
