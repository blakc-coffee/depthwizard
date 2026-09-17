import { JobStatus as JobStatusType, SiltJobStage } from '../../lib/types';

// Mirrors JobStatus.tsx's shape — a dedicated component rather than a
// reused one, since JobStatus hardcodes terrain-specific copy (title, stage
// descriptions) that would be wrong here. Silt's 4 real stages map 1:1 to
// an index, unlike terrain's 7-stage-to-4-card mapping, so this is simpler.
interface SiltJobStatusProps {
  status: JobStatusType;
  stage?: SiltJobStage | null;
  progress?: number | null;
  error?: string | null;
  onRetry?: () => void;
  onReturnToWorkspace?: () => void;
}

const STAGES: { id: SiltJobStage; num: string; label: string; description: string }[] = [
  { id: 'loading_input', num: '01', label: 'Reading imagery', description: 'Loading the uploaded river reach image.' },
  { id: 'estimating_silt', num: '02', label: 'Estimating silt level', description: 'Extracting turbidity features and running the SSC regressor.' },
  { id: 'packaging', num: '03', label: 'Building heatmap', description: 'Packaging the silt heatmap and prediction.' },
  { id: 'uploading_results', num: '04', label: 'Uploading results', description: 'Staging output artifacts.' },
];

function stageIndex(stage?: SiltJobStage | null): number {
  const idx = STAGES.findIndex((s) => s.id === stage);
  return idx === -1 ? 0 : idx;
}

export const SiltJobStatus: React.FC<SiltJobStatusProps> = ({
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
  const currentIndex = stageIndex(stage);
  const current = STAGES[currentIndex];

  return (
    <div className="w-full space-y-6 flex-1">
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading mb-2">
          River Silt Estimation Pipeline
        </h1>
        <p className="text-sm text-slate-500">The model is estimating suspended sediment concentration.</p>
      </div>

      <div className="flex items-center space-x-4 mb-8">
        <div
          className="flex-1 bg-slate-100 rounded-full h-3 overflow-hidden border border-slate-200"
          role="progressbar"
          aria-valuenow={currentProgress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Processing progress"
        >
          <div
            className="bg-[#0F172A] h-full transition-all duration-300 ease-out rounded-full"
            style={{ width: `${currentProgress}%` }}
          />
        </div>
        <span className="font-mono text-sm font-semibold text-slate-900 min-w-[40px] text-right">
          {currentProgress}%
        </span>
      </div>

      {isFailed ? (
        <div role="alert" aria-live="assertive" className="bg-rose-50 border border-rose-200 rounded-xl p-6 space-y-4 max-w-2xl mx-auto text-left">
          <div className="flex items-start space-x-3 text-rose-800">
            <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <h3 className="text-sm font-semibold mb-1 font-heading">Silt Processing Error</h3>
              <p className="text-sm leading-relaxed">{error || 'An unexpected pipeline error occurred.'}</p>
            </div>
          </div>
          <div className="pt-3 border-t border-rose-200 flex flex-wrap gap-3">
            {onReturnToWorkspace && (
              <button type="button" onClick={onReturnToWorkspace} className="bg-[#0F172A] hover:bg-slate-800 text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400">
                Return to Workspace
              </button>
            )}
            {onRetry && (
              <button type="button" onClick={onRetry} className="bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium px-4 py-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400">
                Retry Job
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,360px)] gap-6 items-start w-full">
          <div className="space-y-3 w-full">
            {STAGES.map((st, idx) => {
              const isCurrent = idx === currentIndex && !isCompleted;
              const isPast = idx < currentIndex || isCompleted;
              return (
                <div key={st.id} className={`p-4 rounded-xl border transition-colors flex items-center justify-between ${isCurrent ? 'bg-[#0F172A] text-white border-slate-900 shadow-xs' : 'bg-white border-slate-200 text-slate-800 shadow-2xs'}`}>
                  <div className="flex items-center space-x-3">
                    <span className={`w-8 h-8 rounded-lg font-mono text-xs font-semibold flex items-center justify-center ${isCurrent ? 'bg-white/15 text-white' : 'bg-slate-100 text-slate-700'}`}>
                      {st.num}
                    </span>
                    <div>
                      <h3 className={`text-sm font-semibold font-heading ${isCurrent ? 'text-white' : 'text-slate-900'}`}>{st.label}</h3>
                      <span className={`text-xs ${isCurrent ? 'text-slate-300' : 'text-slate-400'}`}>
                        {isPast ? 'Complete' : isCurrent ? 'In progress' : 'Queued'}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div aria-live="polite" aria-atomic="true" className="bg-white border border-slate-200 rounded-xl p-6 space-y-4 w-full lg:min-w-[320px] lg:max-w-[360px] shadow-xs">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400 block">CURRENT STAGE</span>
            <h2 className="text-xl font-semibold text-slate-900 font-heading">{current.label}</h2>
            <p className="text-xs text-slate-500 leading-relaxed">{current.description}</p>
          </div>
        </div>
      )}
    </div>
  );
};
