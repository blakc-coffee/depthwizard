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

  const stages: { id: string; num: string; label: string }[] = [
    { id: 'loading_input', num: '01', label: 'Reading imagery' },
    { id: 'estimating_depth', num: '02', label: 'Estimating relative depth' },
    { id: 'calibrating', num: '03', label: 'Calibrating elevation' },
    { id: 'uploading_results', num: '04', label: 'Building 3D terrain' },
  ];

  // Map backend stages to active index
  const getStageIndex = (s?: JobStage | null) => {
    if (!s || s === 'loading_input') return 0;
    if (s === 'estimating_depth') return 1;
    if (s === 'fetching_reference' || s === 'calibrating') return 2;
    return 3;
  };

  const currentIndex = getStageIndex(stage);

  return (
    <div className="w-full space-y-6 flex-1">
      {/* Top Header matching image_4.png & Playwright test requirement */}
      <div className="mb-6">
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#36394a] font-heading mb-2">
          Terrain Reconstruction Pipeline
        </h1>
        <p className="text-sm text-[#666d80]">
          The model is building a terrain surface from the uploaded image.
        </p>
      </div>

      {/* Progress Bar Row */}
      <div className="flex items-center space-x-4 mb-8">
        <div
          className="flex-1 bg-[#eceff3] rounded-full h-3 overflow-hidden border border-[#cdd2d9]/40"
          role="progressbar"
          aria-valuenow={currentProgress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Processing progress"
        >
          <div
            className="bg-[#5e4cff] h-full transition-all duration-300 ease-out rounded-full"
            style={{ width: `${currentProgress}%` }}
          />
        </div>
        <span className="font-mono text-sm font-semibold text-[#36394a] min-w-[40px] text-right">
          {currentProgress}%
        </span>
      </div>

      {isFailed ? (
        <div
          role="alert"
          aria-live="assertive"
          className="bg-[#FEE2E2] border border-[#FCA5A5] rounded-[12px] p-6 space-y-4 max-w-2xl mx-auto text-left"
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
              <h3 className="text-sm font-semibold mb-1 font-heading">Terrain Processing Error</h3>
              <p className="text-sm leading-relaxed">{error || 'An unexpected pipeline error occurred.'}</p>
            </div>
          </div>

          <div className="pt-3 border-t border-[#FCA5A5]/60 flex flex-wrap gap-3">
            {onReturnToWorkspace && (
              <button
                type="button"
                onClick={onReturnToWorkspace}
                className="bg-[#5e4cff] hover:bg-[#5e4cff]/90 text-white text-xs font-medium px-4 py-2 rounded-[8px] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
              >
                Return to Workspace
              </button>
            )}
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="bg-white hover:bg-[#f6f8fa] border border-[#cdd2d9] text-[#36394a] text-xs font-medium px-4 py-2 rounded-[8px] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
              >
                Retry Job
              </button>
            )}
          </div>
        </div>
      ) : (
        /* Two Column Stage Grid matching image_4.png */
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,360px)] gap-6 items-start w-full">
          {/* Left Stage Cards */}
          <div className="space-y-3 w-full">
            {stages.map((st, idx) => {
              const isCurrent = idx === currentIndex && !isCompleted;
              const isPast = idx < currentIndex || isCompleted;

              return (
                <div
                  key={st.id}
                  className={`p-4 rounded-[12px] border transition-colors flex items-center justify-between ${
                    isCurrent
                      ? 'bg-[#5e4cff] text-white border-[#5e4cff]'
                      : 'bg-white border-[#cdd2d9] text-[#36394a]'
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <span
                      className={`w-8 h-8 rounded-[8px] font-mono text-xs font-semibold flex items-center justify-center ${
                        isCurrent
                          ? 'bg-white/20 text-white'
                          : 'bg-[#dfdbff] text-[#5e4cff]'
                      }`}
                    >
                      {st.num}
                    </span>
                    <div>
                      <h3
                        className={`text-sm font-semibold font-heading ${
                          isCurrent ? 'text-white' : 'text-[#36394a]'
                        }`}
                      >
                        {st.label}
                      </h3>
                      <span
                        className={`text-xs ${
                          isCurrent ? 'text-white/80' : 'text-[#818898]'
                        }`}
                      >
                        {isPast ? 'Complete' : isCurrent ? 'In progress' : 'Queued'}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Right Column: CURRENT STAGE Card */}
          <div
            aria-live="polite"
            aria-atomic="true"
            className="bg-white border border-[#cdd2d9] rounded-[12px] p-6 space-y-4 w-full lg:min-w-[320px] lg:max-w-[360px]"
          >
            <span className="text-xs font-mono uppercase tracking-wider text-[#818898] block">
              CURRENT STAGE
            </span>

            <h2 className="text-xl font-semibold text-[#36394a] font-heading">
              {formatStageLabel(stage)}
            </h2>

            <p className="text-xs text-[#666d80] leading-relaxed">
              {stage === 'calibrating' || stage === 'fetching_reference'
                ? 'Fusing scene statistics with reference elevation signals.'
                : stage === 'estimating_depth'
                ? 'Running monocular depth estimation network on input pixels.'
                : 'Processing geospatial data pipeline for 3D reconstruction.'}
            </p>

            <div className="bg-[#dfdbff]/50 border border-[#c8ccf3] text-[#5e4cff] rounded-[8px] p-3 text-xs font-mono font-medium">
              Estimated time remaining · 18 s
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
