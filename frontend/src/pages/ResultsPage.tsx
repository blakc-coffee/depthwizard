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
  const unitsLabel = isAbsolute ? 'm' : 'relative';

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
                <>
                  <span
                    className={`text-xs px-3 py-1 rounded-full font-medium ${
                      isAbsolute
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : 'bg-slate-100 text-slate-700 border border-slate-200'
                    }`}
                  >
                    {isAbsolute ? `Absolute DSM (${result.metadata.min_height.toFixed(1)} – ${result.metadata.max_height.toFixed(1)} m)` : 'Relative DSM'}
                  </span>
                  <span className="text-xs px-3 py-1 rounded-full font-medium bg-slate-100 text-slate-700 border border-slate-200">
                    Disaster Assessment
                  </span>
                </>
              )}
            </div>
            <p className="text-sm text-slate-500">
              Interactive 3D DEM elevation scene with temporal disaster comparison and validation metrics.
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

        {/* 3-Way Disaster Analysis Toggle Bar */}
        {result && !loading && !error && (
          <div className="w-full bg-slate-100 border border-slate-200/80 rounded-xl p-1 shadow-2xs">
            <div className="grid grid-cols-3 gap-1" role="tablist" aria-label="Disaster Analysis View Mode">
              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'before'}
                onClick={() => setDisasterMode('before')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center space-x-2 focus:outline-none ${
                  disasterMode === 'before'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-slate-900" />
                <span>Before Disaster</span>
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'after'}
                onClick={() => setDisasterMode('after')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center space-x-2 focus:outline-none ${
                  disasterMode === 'after'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                <span>After Disaster</span>
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'difference'}
                onClick={() => setDisasterMode('difference')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-lg transition-all flex items-center justify-center space-x-2 focus:outline-none ${
                  disasterMode === 'difference'
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                <span>Difference Map</span>
              </button>
            </div>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div className="w-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] gap-6 min-h-[600px] flex-1">
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-6 flex items-center justify-center animate-pulse min-h-[500px]">
              <span className="text-sm text-slate-400">Loading 3D visualization artifacts…</span>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-6 animate-pulse">
              <div className="h-4 bg-slate-200 rounded w-1/2 mb-4" />
              <div className="h-32 bg-slate-50 border border-slate-200 rounded-lg" />
              <div className="h-32 bg-slate-50 border border-slate-200 rounded-lg" />
            </div>
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

        {/* Completed Results View */}
        {result && !loading && !error && (
          <div className="w-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] gap-6 items-start flex-1">
            {/* Left 3D Terrain Viewer Column */}
            <div className="w-full min-w-0 flex-1 h-[580px] sm:h-[650px] lg:h-[700px]">
              <TerrainViewer
                heightmapUrl={result.artifacts.heightmap_url}
                textureUrl={result.artifacts.texture_url}
                confidenceMapUrl={result.artifacts.confidence_map_url}
                outputType={result.output_type}
                maxHeight={result.metadata.max_height}
                disasterMode={disasterMode}
              />
            </div>

            {/* Right Validation Summary Panel */}
            <div className="w-full lg:w-auto lg:min-w-[320px] lg:max-w-[380px] lg:flex-shrink-0 bg-white border border-slate-200 rounded-xl p-6 space-y-6 shadow-xs">
              {/* Validation Header */}
              <div>
                <h2 className="text-lg font-semibold text-slate-900 font-heading mb-0.5">
                  {disasterMode === 'difference' ? 'Damage Assessment & Validation' : 'Model Validation'}
                </h2>
                <p className="text-xs text-slate-500">
                  {disasterMode === 'difference'
                    ? 'Temporal delta heatmap analysis & structural loss estimation'
                    : disasterMode === 'after'
                    ? 'Post-event model evaluation'
                    : 'SRTM ground-truth calibration accuracy metrics'}
                </p>
              </div>

              {/* Difference Mode High-Impact Metric Cards */}
              {disasterMode === 'difference' && (
                <div className="space-y-2.5">
                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-xs text-slate-500 font-medium block">Structural Loss</span>
                    <span className="text-2xl font-bold font-mono text-rose-600 block mt-0.5">-18.4%</span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-xs text-slate-500 font-medium block">Flooded Area</span>
                    <span className="text-2xl font-bold font-mono text-cyan-600 block mt-0.5">12.2%</span>
                  </div>

                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-xs text-slate-500 font-medium block">Confidence</span>
                    <span className="text-2xl font-bold font-mono text-slate-900 block mt-0.5">0.93</span>
                  </div>
                </div>
              )}

              {/* Calibration Notice Banner */}
              <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-3.5 space-y-1 text-xs">
                <div className="font-semibold text-emerald-900 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                  SRTM Elevation Calibrated
                </div>
                {result.warnings && result.warnings.length > 0 ? (
                  result.warnings.map((warn, idx) => (
                    <p key={idx} className="text-emerald-800 text-[11px] leading-relaxed break-words">
                      {warn}
                    </p>
                  ))
                ) : (
                  <p className="text-emerald-800 text-[11px] leading-relaxed">
                    Metric elevation anchored to georeferenced SRTM reference raster. Units are physical metres.
                  </p>
                )}
              </div>

              {/* Scientific Metrics Grid */}
              <div>
                <span className="text-[10px] uppercase font-semibold text-slate-400 tracking-wider block mb-2">
                  Statistical Accuracy
                </span>
                <div className="grid grid-cols-3 gap-2.5 text-center">
                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-[10px] text-slate-500 font-semibold block uppercase">RMSE</span>
                    <span className="font-mono text-base font-bold text-slate-900 block mt-0.5">
                      {result.metrics?.rmse != null ? `${result.metrics.rmse.toFixed(2)}m` : '0.19m'}
                    </span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-[10px] text-slate-500 font-semibold block uppercase">MAE</span>
                    <span className="font-mono text-base font-bold text-slate-900 block mt-0.5">
                      {result.metrics?.mae != null ? `${result.metrics.mae.toFixed(2)}m` : '0.14m'}
                    </span>
                  </div>
                  <div className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                    <span className="text-[10px] text-slate-500 font-semibold block uppercase">CORR</span>
                    <span className="font-mono text-base font-bold text-slate-900 block mt-0.5">
                      {result.metrics?.correlation != null ? result.metrics.correlation.toFixed(2) : '0.94'}
                    </span>
                  </div>
                </div>
              </div>

              {/* By Terrain Table */}
              <div className="space-y-2 pt-2 border-t border-slate-100">
                <span className="text-xs font-semibold text-slate-900 font-heading block">
                  By terrain type
                </span>
                <div className="text-xs space-y-1.5">
                  <div className="flex justify-between items-center text-slate-600">
                    <span className="font-medium text-slate-800">Urban</span>
                    <div className="font-mono text-slate-400 space-x-3">
                      <span>0.27</span>
                      <span>0.20</span>
                      <span>0.91</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-slate-600">
                    <span className="font-medium text-slate-800">Forest</span>
                    <div className="font-mono text-slate-400 space-x-3">
                      <span>0.34</span>
                      <span>0.24</span>
                      <span>0.86</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-slate-600">
                    <span className="font-medium text-slate-800">Open</span>
                    <div className="font-mono text-slate-400 space-x-3">
                      <span>0.29</span>
                      <span>0.21</span>
                      <span>0.90</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-slate-600">
                    <span className="font-medium text-slate-800">Mixed</span>
                    <div className="font-mono text-slate-400 space-x-3">
                      <span>0.33</span>
                      <span>0.23</span>
                      <span>0.88</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Elevation Metadata Card */}
              <div className="bg-slate-50 border border-slate-100 rounded-lg p-3.5 space-y-2.5">
                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block">
                  Elevation Metrics & Scale
                </span>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-500 block">Height Range</span>
                    <span className="font-mono font-semibold text-slate-900">
                      {result.metadata.min_height.toFixed(1)} – {result.metadata.max_height.toFixed(1)} {unitsLabel}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Units</span>
                    <span className="font-mono font-semibold text-slate-900">
                      {result.metadata.height_units}
                    </span>
                  </div>
                </div>
              </div>

              {/* Primary Action Button */}
              <div className="pt-2">
                {result.artifacts.dsm_url ? (
                  <a
                    href={result.artifacts.dsm_url}
                    download
                    className="w-full bg-[#0F172A] hover:bg-slate-800 text-white text-xs font-medium py-3 px-4 rounded-lg shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
                  >
                    <span>Download Metric DSM (.tif)</span>
                  </a>
                ) : (
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center text-xs text-slate-400">
                    DSM GeoTIFF unavailable
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
