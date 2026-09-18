import { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { TerrainViewer } from '../components/viewer/TerrainViewer';
import { ComparisonTerrainParams, DisasterMode } from '../viewer/TerrainSceneManager';
import { useComparePolling } from '../hooks/useComparePolling';
import { getCompareResult, getJobResult } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { CompareResultResponse, JobResult } from '../lib/types';

export const ResultsPage = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const [searchParams] = useSearchParams();
  const compareId = searchParams.get('compare') || undefined;
  const navigate = useNavigate();

  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [disasterMode, setDisasterMode] = useState<DisasterMode>('before');

  // Real comparison data only — no fallback to fabricated "after"/"difference"
  // terrain. Undefined until the backend-computed compare actually finishes.
  const { compareData, error: compareError } = useComparePolling(compareId);
  const [compareResult, setCompareResult] = useState<CompareResultResponse | null>(null);
  const [afterJobResult, setAfterJobResult] = useState<JobResult | null>(null);
  const [comparisonLoadError, setComparisonLoadError] = useState<string | null>(null);

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

  // Once the compare job itself reports 'completed', fetch its real result
  // (diff map + metadata) and the "after" job's own real artifacts (its
  // heightmap isn't part of CompareResultResponse — the compare endpoint
  // only carries the diff map and both textures, so the after job's own
  // /result is the real source for its heightmap).
  useEffect(() => {
    if (compareData?.status !== 'completed' || !compareId) return;

    let isMounted = true;
    getCompareResult(compareId)
      .then((cmp) => {
        if (!isMounted) return;
        setCompareResult(cmp);
        return getJobResult(cmp.after_job_id);
      })
      .then((after) => {
        if (isMounted && after) setAfterJobResult(after);
      })
      .catch((err) => {
        if (isMounted) setComparisonLoadError(getFriendlyErrorMessage(err));
      });

    return () => {
      isMounted = false;
    };
  }, [compareData?.status, compareId]);

  const handleReturnToWorkspace = () => {
    navigate('/app');
  };

  const comparisonReady = Boolean(compareResult && afterJobResult);
  const comparisonFailed = compareData?.status === 'failed' || Boolean(comparisonLoadError) || Boolean(compareError);
  const comparisonPending = Boolean(compareId) && !comparisonReady && !comparisonFailed;

  const comparisonParams: ComparisonTerrainParams | null =
    comparisonReady && compareResult && afterJobResult
      ? {
          afterHeightmapUrl: afterJobResult.artifacts.heightmap_url,
          afterTextureUrl: compareResult.artifacts.after_texture_url,
          diffMapUrl: compareResult.artifacts.diff_map_url,
        }
      : null;

  // "After"/"Difference" tabs are only real once the comparison finished —
  // clicking them before that just stays on 'before' rather than rendering
  // a mode with nothing registered for it (see TerrainSceneManager.loadTerrain).
  const handleModeSelect = (mode: DisasterMode) => {
    if (mode !== 'before' && !comparisonReady) return;
    setDisasterMode(mode);
  };

  return (
    <AppShell>
      <div className="w-full flex-1 flex flex-col space-y-6">
        {/* Header Title Row */}
        <div className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading">
                Terrain Reconstruction Results
              </h1>
            </div>
            <p className="text-sm text-slate-500">
              {compareId
                ? 'Interactive 3D DEM elevation scene with temporal disaster comparison.'
                : 'Interactive 3D DEM elevation scene.'}
            </p>
          </div>

          <div className="flex items-center space-x-3 self-start sm:self-center">
            <span className="text-xs font-mono text-slate-400 hidden sm:inline-block">
              Job: {jobId || 'Unknown'}
            </span>
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="text-xs bg-[#0F172A] hover:bg-slate-800 text-white font-medium px-4 py-2 rounded-lg shadow-xs transition-colors flex-shrink-0"
            >
              New Terrain Job
            </button>
          </div>
        </div>

        {/* 3-Way Disaster Analysis tab strip — only rendered when a real
            comparison was requested (compareId present). A single-image job
            has no "after"/"difference" to show, so it just shows the terrain. */}
        {result && !loading && !error && compareId && (
          <div className="w-full bg-slate-100 rounded-lg p-1">
            <div className="flex items-center" role="tablist" aria-label="Disaster Analysis View Mode">
              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'before'}
                onClick={() => handleModeSelect('before')}
                className={`flex-1 py-2 px-3 text-xs sm:text-sm font-medium rounded-md transition-all text-center focus:outline-none ${
                  disasterMode === 'before'
                    ? 'bg-[#5e4cff] text-white shadow-xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Before Disaster
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'after'}
                onClick={() => handleModeSelect('after')}
                disabled={!comparisonReady}
                className={`flex-1 py-2 px-3 text-xs sm:text-sm font-medium rounded-md transition-all text-center focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed ${
                  disasterMode === 'after'
                    ? 'bg-[#5e4cff] text-white shadow-xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                After Disaster{comparisonPending ? ' · generating…' : comparisonFailed ? ' · unavailable' : ''}
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'difference'}
                onClick={() => handleModeSelect('difference')}
                disabled={!comparisonReady}
                className={`flex-1 py-2 px-3 text-xs sm:text-sm font-medium rounded-md transition-all text-center focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed ${
                  disasterMode === 'difference'
                    ? 'bg-[#5e4cff] text-white shadow-xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Difference Map{comparisonPending ? ' · generating…' : comparisonFailed ? ' · unavailable' : ''}
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

        {/* Completed Results View: 2 Major Zones (Viewer + Single Unboxed Sidebar Panel) */}
        {result && !loading && !error && (
          <div className="w-full grid grid-cols-1 lg:grid-cols-[1fr_300px] xl:grid-cols-[1fr_340px] gap-6 items-start flex-1">
            {/* Zone 1: 3D Terrain Viewer Canvas */}
            <div className="w-full min-w-0 h-[600px] sm:h-[680px] lg:h-[740px]">
              <TerrainViewer
                heightmapUrl={result.artifacts.heightmap_url}
                textureUrl={result.artifacts.texture_url}
                confidenceMapUrl={result.artifacts.confidence_map_url}
                outputType={result.output_type}
                maxHeight={result.metadata.max_height}
                disasterMode={disasterMode}
                comparison={comparisonParams}
              />
            </div>

            {/* Zone 2: Single Sidebar Panel (Rule 2: at most one outer boundary, no nested boxes) */}
            <aside className="w-full bg-white rounded-xl border border-slate-200/80 p-6 space-y-6 shadow-xs">
              {/* Panel Header */}
              <div>
                <h2 className="text-base font-semibold text-slate-900 font-heading">
                  {disasterMode === 'difference' ? 'Damage Assessment' : 'Model Evaluation'}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {disasterMode === 'difference'
                    ? 'Real per-pixel height change, computed from both DSMs'
                    : 'Georeferenced elevation metrics & scale'}
                </p>
              </div>

              {/* Statistical Accuracy / Metrics (Rule 1 & 2: Plain label/value pairs, no boxed cards) */}
              {disasterMode === 'difference' ? (
                comparisonReady && compareResult ? (
                  <div className="space-y-3.5">
                    <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider block">
                      Temporal Delta ({compareResult.metadata.height_units === 'm' ? 'metres' : 'relative units'})
                    </span>
                    <div className="flex justify-between items-baseline py-0.5">
                      <span className="text-xs text-slate-600">Max Height Lost</span>
                      <span className="font-mono text-base font-bold text-rose-600">
                        {compareResult.metadata.max_loss.toFixed(2)}
                        {compareResult.metadata.height_units === 'm' ? 'm' : ''}
                      </span>
                    </div>
                    <div className="flex justify-between items-baseline py-0.5">
                      <span className="text-xs text-slate-600">Max Height Gained</span>
                      <span className="font-mono text-base font-bold text-cyan-600">
                        +{compareResult.metadata.max_gain.toFixed(2)}
                        {compareResult.metadata.height_units === 'm' ? 'm' : ''}
                      </span>
                    </div>
                    <div className="flex justify-between items-baseline py-0.5">
                      <span className="text-xs text-slate-600">Changed Area</span>
                      <span className="font-mono text-base font-bold text-slate-900">
                        {(compareResult.metadata.changed_area_fraction * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between items-baseline py-0.5">
                      <span className="text-xs text-slate-600">Change Threshold</span>
                      <span className="font-mono text-xs font-semibold text-slate-900">
                        {compareResult.metadata.threshold.toFixed(2)}
                        {compareResult.metadata.height_units === 'm' ? 'm' : ''}
                      </span>
                    </div>
                    {compareResult.warnings.length > 0 && (
                      <div className="pt-2 space-y-1">
                        {compareResult.warnings.map((w, i) => (
                          <p key={i} className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5">
                            {w}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">
                    {comparisonFailed
                      ? 'The comparison could not be computed for these two jobs.'
                      : 'Comparison is still processing…'}
                  </p>
                )
              ) : (
                <div className="space-y-3.5">
                  <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider block">
                    Statistical Accuracy
                  </span>
                  {result.metrics ? (
                    <>
                      <div className="flex justify-between items-baseline py-0.5">
                        <span className="text-xs text-slate-600">RMSE</span>
                        <span className="font-mono text-base font-bold text-slate-900">
                          {result.metrics.rmse.toFixed(2)}m
                        </span>
                      </div>
                      <div className="flex justify-between items-baseline py-0.5">
                        <span className="text-xs text-slate-600">MAE</span>
                        <span className="font-mono text-base font-bold text-slate-900">
                          {result.metrics.mae.toFixed(2)}m
                        </span>
                      </div>
                      <div className="flex justify-between items-baseline py-0.5">
                        <span className="text-xs text-slate-600">Correlation (R²)</span>
                        <span className="font-mono text-base font-bold text-slate-900">
                          {result.metrics.correlation.toFixed(2)}
                        </span>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-slate-400">
                      Not available — this scene has no reference elevation data to score against.
                    </p>
                  )}
                </div>
              )}

              {/* Elevation Scale & Units (Rule 1 & 6: Plain label/value pairs, no divider) */}
              <div className="pt-2 space-y-3.5">
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider block">
                  Elevation Metrics
                </span>
                <div className="flex justify-between items-baseline py-0.5">
                  <span className="text-xs text-slate-600">Height Range</span>
                  <span className="font-mono text-xs font-semibold text-slate-900">
                    {result.metadata.min_height.toFixed(1)} – {result.metadata.max_height.toFixed(1)} m
                  </span>
                </div>
                <div className="flex justify-between items-baseline py-0.5">
                  <span className="text-xs text-slate-600">Elevation Units</span>
                  <span className="font-mono text-xs font-semibold text-slate-900">
                    {result.metadata.height_units}
                  </span>
                </div>
              </div>

              {/* Action Button (Rule 7: Accent indigo on interactive action) */}
              <div className="pt-2">
                {result.artifacts.dsm_url ? (
                  <a
                    href={result.artifacts.dsm_url}
                    download
                    className="w-full bg-[#5e4cff] hover:bg-[#4f3ef0] text-white text-xs font-medium py-2.5 px-4 rounded-lg shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff]/40"
                  >
                    <span>Download Metric DSM (.tif)</span>
                  </a>
                ) : (
                  <div className="text-center text-xs text-slate-400 py-1">
                    DSM GeoTIFF unavailable
                  </div>
                )}
              </div>
            </aside>
          </div>
        )}
      </div>
    </AppShell>
  );
};
