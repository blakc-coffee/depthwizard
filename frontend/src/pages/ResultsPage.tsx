import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { TerrainViewer } from '../components/viewer/TerrainViewer';
import { DisasterMode } from '../viewer/TerrainSceneManager';
import { getJobResult } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { JobResult } from '../lib/types';

export const ResultsPage = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [disasterMode, setDisasterMode] = useState<DisasterMode>('before');

  useEffect(() => {
    document.title = 'DepthWizard | Terrain Results';
  }, []);

  useEffect(() => {
    if (!jobId) {
      setError('No Job ID specified.');
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    getJobResult(jobId)
      .then((res) => {
        if (isMounted) {
          setResult(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(getFriendlyErrorMessage(err));
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [jobId]);

  const handleReturnToWorkspace = () => {
    navigate('/app');
  };

  const isAbsolute = result?.output_type === 'absolute_dsm';

  return (
    <AppShell>
      <div className="w-full flex-1 flex flex-col space-y-6">
        {/* Header Title Row */}
        <div className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading">
                Terrain Reconstruction Results
              </h1>
              {result && (
                <span className="text-xs px-3 py-1 rounded-full font-medium bg-slate-100 text-slate-700 border border-slate-200">
                  {isAbsolute ? `Absolute DSM (${result.metadata.min_height.toFixed(1)} – ${result.metadata.max_height.toFixed(1)} m)` : 'Relative DSM'}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500">
              Interactive 3D DEM elevation scene with temporal disaster comparison.
            </p>
          </div>

          <div className="flex items-center space-x-3 self-start sm:self-center">
            <span className="text-xs font-mono text-slate-400 hidden sm:inline-block">
              Job: {jobId || 'Unknown'}
            </span>
            {result?.artifacts?.dsm_url && (
              <a
                href={result.artifacts.dsm_url}
                download
                className="text-xs bg-white hover:bg-slate-50 text-slate-700 font-medium px-3.5 py-2 rounded-lg border border-slate-200 shadow-2xs transition-colors flex items-center space-x-1.5 flex-shrink-0"
              >
                <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Download DSM (.tif)</span>
              </a>
            )}
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="text-xs bg-[#0F172A] hover:bg-slate-800 text-white font-medium px-4 py-2 rounded-lg shadow-xs transition-colors flex-shrink-0"
            >
              New Terrain Job
            </button>
          </div>
        </div>

        {/* 3-Way Disaster Analysis Toggle Bar (Clean text tabs without colored indicator dots) */}
        {result && !loading && !error && (
          <div className="w-full bg-slate-100 border border-slate-200/80 rounded-xl p-1 shadow-2xs">
            <div className="grid grid-cols-3 gap-1" role="tablist" aria-label="Disaster Analysis View Mode">
              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'before'}
                onClick={() => setDisasterMode('before')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center focus:outline-none ${
                  disasterMode === 'before'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Before Disaster
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'after'}
                onClick={() => setDisasterMode('after')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center focus:outline-none ${
                  disasterMode === 'after'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                After Disaster
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'difference'}
                onClick={() => setDisasterMode('difference')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center focus:outline-none ${
                  disasterMode === 'difference'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Difference Map
              </button>
            </div>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div className="w-full min-h-[600px] flex-1 bg-slate-50 border border-slate-200 rounded-xl p-6 flex items-center justify-center animate-pulse">
            <span className="text-sm text-slate-400">Loading 3D visualization artifacts…</span>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="max-w-2xl mx-auto bg-rose-50 border border-rose-200 rounded-xl p-6 space-y-4 text-left my-auto">
            <div className="flex items-start space-x-3 text-rose-800">
              <svg
                className="w-6 h-6 flex-shrink-0 mt-0.5"
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
                <h2 className="text-base font-semibold mb-1 font-heading">Results Unavailable</h2>
                <p className="text-sm">{error}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="bg-[#0F172A] hover:bg-slate-800 text-white text-xs font-medium px-4 py-2 rounded-lg shadow-xs transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              Return to Workspace
            </button>
          </div>
        )}

        {/* Completed Results View - Full Width Seamless 3D Studio Canvas */}
        {result && !loading && !error && (
          <div className="w-full flex-1">
            <div className="w-full h-[620px] sm:h-[700px] lg:h-[780px]">
              <TerrainViewer
                heightmapUrl={result.artifacts.heightmap_url}
                textureUrl={result.artifacts.texture_url}
                confidenceMapUrl={result.artifacts.confidence_map_url}
                outputType={result.output_type}
                maxHeight={result.metadata.max_height}
                disasterMode={disasterMode}
              />
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
