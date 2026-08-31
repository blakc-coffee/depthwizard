import { JobStage, JobStatus as JobStatusType } from '../../lib/types';

interface JobStatusProps {
  status: JobStatusType;
  stage?: JobStage | null;
  progress?: number | null;
  error?: string | null;
  onRetry?: () => void;
  onReturnToWorkspace?: () => void;
}

export function formatStageLabel(stage?: JobStage | null): string {
  if (!stage) return 'Initializing…';
  switch (stage) {
    case 'loading_input':
      return 'Loading Input…';
    case 'estimating_depth':
      return 'Estimating Depth…';
    case 'fetching_reference':
      return 'Fetching Reference…';
    case 'calibrating':
      return 'Calibrating Elevation…';
    case 'packaging':
      return 'Packaging Results…';
    case 'validating_output':
      return 'Validating Output…';
    case 'uploading_results':
      return 'Uploading Results…';
    default: {
      const formatted = String(stage).replace(/_/g, ' ');
      return formatted.charAt(0).toUpperCase() + formatted.slice(1) + '…';
    }
  }
}

export function formatStatusLabel(status: JobStatusType): string {
  switch (status) {
    case 'queued':
      return 'Queued — Waiting for processing worker';
    case 'processing':
      return 'Processing — Running terrain pipeline';
    case 'completed':
      return 'Completed — Preparing visualization';
    case 'failed':
      return 'Failed — Pipeline execution stopped';
  }
}

export const JobStatus: React.FC<JobStatusProps> = ({
  status,
  stage,
  progress,
  error,
  onRetry,
  onReturnToWorkspace,
}) => {
  const currentProgress = Math.min(100, Math.max(0, progress ?? 0));
  const isFailed = status === 'failed';
  const isCompleted = status === 'completed';

  return (
    <div className="w-full max-w-2xl mx-auto space-y-6">
      <div className="bg-[#FDFCF8] border border-gray-200 rounded-xl p-6 sm:p-8 shadow-sm text-left">
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
          <div>
            <span className="text-xs font-mono uppercase tracking-wider text-gray-500 block mb-1">
              Pipeline Status
            </span>
            <h2 className="text-xl font-semibold text-gray-900 flex items-center space-x-2">
              <span>{formatStatusLabel(status)}</span>
            </h2>
          </div>

          <div className="flex items-center space-x-2">
            {!isFailed && !isCompleted && (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-[#DDEED9] text-emerald-800 border border-emerald-200">
                <span className="w-2 h-2 rounded-full bg-[#639A67] animate-pulse mr-1.5" />
                Active
              </span>
            )}
            {isCompleted && (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800 border border-green-200">
                Completed
              </span>
            )}
            {isFailed && (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800 border border-red-200">
                Failed
              </span>
            )}
          </div>
        </div>

        {isFailed ? (
          <div
            role="alert"
            aria-live="assertive"
            className="bg-[#FEE2E2] border border-[#FCA5A5] rounded-lg p-5 space-y-3 mb-6"
          >
            <div className="flex items-start space-x-3 text-[#991B1B]">
              <svg
                className="w-5 h-5 flex-shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div>
                <h3 className="text-sm font-semibold mb-1">Terrain Processing Error</h3>
                <p className="text-sm leading-relaxed">{error || 'An unexpected pipeline error occurred.'}</p>
              </div>
            </div>

            <div className="pt-3 border-t border-red-200 flex flex-wrap gap-3">
              {onReturnToWorkspace && (
                <button
                  type="button"
                  onClick={onReturnToWorkspace}
                  className="bg-purple-700 hover:bg-purple-800 text-white text-xs font-medium px-4 py-2 rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600"
                >
                  Return to Workspace
                </button>
              )}
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="bg-[#FDFCF8] hover:bg-[#ECE9DD] border border-gray-300 text-gray-800 text-xs font-medium px-4 py-2 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600"
                >
                  Retry Job
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <div className="flex justify-between items-center text-sm font-medium mb-2">
                <span className="text-gray-800">{formatStageLabel(stage)}</span>
                <span className="font-mono text-gray-900 font-bold tabular-nums">
                  {currentProgress}%
                </span>
              </div>

              <div
                className="w-full bg-[#ECE9DD] rounded-full h-3.5 overflow-hidden shadow-inner"
                role="progressbar"
                aria-valuenow={currentProgress}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Processing progress"
              >
                <div
                  className="bg-[#639A67] h-full transition-all duration-300 ease-out rounded-full"
                  style={{ width: `${currentProgress}%` }}
                />
              </div>
            </div>

            <div
              aria-live="polite"
              aria-atomic="true"
              className="bg-[#ECE9DD]/40 rounded-md p-3.5 text-xs text-gray-600 border border-[#ECE9DD] flex items-center justify-between"
            >
              <span>Current Stage: {stage ? String(stage) : 'initializing'}</span>
              <span className="font-mono text-gray-500">Backend Status: {status}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
