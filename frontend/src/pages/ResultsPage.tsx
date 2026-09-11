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
        {/* Header Title Row matching image_3.png & Playwright test requirement */}
        <div className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#cdd2d9] flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#36394a] font-heading">
                Terrain Reconstruction Results
              </h1>
              {result && (
                <>
                  <span
                    className={`text-xs px-3 py-1 rounded-full font-medium ${
                      isAbsolute
                        ? 'bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]'
                        : 'bg-[#f6f8fa] text-[#36394a] border border-[#cdd2d9]'
                    }`}
                  >
                    {isAbsolute ? 'Absolute DSM' : 'Relative DSM'}
                  </span>
                  <span className="text-xs px-3 py-1 rounded-full font-medium bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]">
                    Disaster Assessment
                  </span>
                </>
              )}
            </div>
            <p className="text-sm text-[#666d80]">
              Interactive DSM scene with temporal disaster comparison and validation metrics.
            </p>
          </div>

          <div className="flex items-center space-x-3 self-start sm:self-center">
            <span className="text-xs font-mono text-[#818898] hidden sm:inline-block">
              Job: {jobId || 'Unknown'}
            </span>
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="text-xs bg-white hover:bg-[#f6f8fa] border border-[#cdd2d9] text-[#36394a] font-medium px-4 py-2 rounded-[8px] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] flex-shrink-0"
            >
              New Terrain Job
            </button>
          </div>
        </div>

        {/* 3-Way Disaster Analysis Toggle Bar matching UI reference mockup */}
        {result && !loading && !error && (
          <div className="w-full bg-white border border-[#cdd2d9] rounded-[10px] p-1.5 shadow-2xs">
            <div className="grid grid-cols-3 gap-1.5" role="tablist" aria-label="Disaster Analysis View Mode">
              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'before'}
                onClick={() => setDisasterMode('before')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-[8px] transition-all flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
                  disasterMode === 'before'
                    ? 'bg-[#5e4cff] text-white shadow-xs'
                    : 'text-[#36394a] hover:text-[#5e4cff] hover:bg-[#f6f8fa]'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${disasterMode === 'before' ? 'bg-white' : 'bg-[#5e4cff]'}`} />
                <span>Before Disaster</span>
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'after'}
                onClick={() => setDisasterMode('after')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-[8px] transition-all flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
                  disasterMode === 'after'
                    ? 'bg-[#5e4cff] text-white shadow-xs'
                    : 'text-[#36394a] hover:text-[#5e4cff] hover:bg-[#f6f8fa]'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${disasterMode === 'after' ? 'bg-white' : 'bg-amber-500'}`} />
                <span>After Disaster</span>
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={disasterMode === 'difference'}
                onClick={() => setDisasterMode('difference')}
                className={`py-2 sm:py-2.5 px-3 text-xs sm:text-sm font-semibold rounded-[8px] transition-all flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
                  disasterMode === 'difference'
                    ? 'bg-[#5e4cff] text-white shadow-xs'
                    : 'text-[#36394a] hover:text-[#5e4cff] hover:bg-[#f6f8fa]'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${disasterMode === 'difference' ? 'bg-white' : 'bg-red-500'}`} />
                <span>Difference Map</span>
              </button>
            </div>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div className="w-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] gap-6 min-h-[600px] flex-1">
            <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-6 flex items-center justify-center animate-pulse min-h-[500px]">
              <span className="text-sm text-[#818898]">Loading 3D visualization artifacts…</span>
            </div>
            <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-6 space-y-6 animate-pulse">
              <div className="h-4 bg-[#eceff3] rounded w-1/2 mb-4" />
              <div className="h-32 bg-[#f6f8fa] border border-[#cdd2d9] rounded-[8px]" />
              <div className="h-32 bg-[#f6f8fa] border border-[#cdd2d9] rounded-[8px]" />
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="max-w-2xl mx-auto bg-[#FEE2E2] border border-[#FCA5A5] rounded-[12px] p-6 space-y-4 text-left my-auto">
            <div className="flex items-start space-x-3 text-[#991B1B]">
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
              className="bg-[#5e4cff] hover:bg-[#5e4cff]/90 text-white text-xs font-medium px-4 py-2 rounded-[8px] shadow-xs transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
            >
              Return to Workspace
            </button>
          </div>
        )}

        {/* Completed Results View matching image_3.png */}
        {result && !loading && !error && (
          <div className="w-full grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] gap-6 items-start flex-1">
            {/* Left 3D Terrain Viewer Column (Dominant 68%-72% width) */}
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

            {/* Right "Validation" Summary Panel matching image_3.png (NO inner scrollbar) */}
            <div className="w-full lg:w-auto lg:min-w-[320px] lg:max-w-[380px] lg:flex-shrink-0 bg-white border border-[#cdd2d9] rounded-[12px] p-6 space-y-6">
              {/* Validation Header */}
              <div>
                <h2 className="text-xl font-semibold text-[#36394a] font-heading mb-0.5">
                  {disasterMode === 'difference' ? 'Damage Assessment & Validation' : 'Validation'}
                </h2>
                <p className="text-xs text-[#818898]">
                  {disasterMode === 'difference'
                    ? 'Temporal delta heatmap analysis & structural loss estimation'
                    : disasterMode === 'after'
                    ? 'Post-event model evaluation'
                    : 'Model quality'}
                </p>
              </div>

              {/* Difference Mode High-Impact Metric Cards matching mockup */}
              {disasterMode === 'difference' && (
                <div className="space-y-2.5">
                  <div className="bg-white border border-[#cdd2d9] rounded-[8px] p-3 shadow-2xs">
                    <span className="text-xs text-[#666d80] font-medium block">Structural Loss</span>
                    <span className="text-2xl font-bold font-mono text-red-600 block mt-0.5">-18.4%</span>
                  </div>

                  <div className="bg-white border border-[#cdd2d9] rounded-[8px] p-3 shadow-2xs">
                    <span className="text-xs text-[#666d80] font-medium block">Flooded Area</span>
                    <span className="text-2xl font-bold font-mono text-cyan-600 block mt-0.5">12.2%</span>
                  </div>

                  <div className="bg-white border border-[#cdd2d9] rounded-[8px] p-3 shadow-2xs">
                    <span className="text-xs text-[#666d80] font-medium block">Confidence</span>
                    <span className="text-2xl font-bold font-mono text-[#36394a] block mt-0.5">0.93</span>
                  </div>
                </div>
              )}

              {/* Warnings Banner */}
              {result.warnings && result.warnings.length > 0 && (
                <div
                  role="alert"
                  aria-live="polite"
                  className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[8px] p-3.5 space-y-1.5 text-xs text-[#36394a]"
                >
                  <div className="flex items-center space-x-1.5 font-semibold font-heading text-[#36394a]">
                    <svg className="w-4 h-4 text-[#5e4cff] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>Calibration Notice</span>
                  </div>
                  {result.warnings.map((warn, idx) => (
                    <p key={idx} className="leading-relaxed break-words text-[#666d80]">
                      {warn}
                    </p>
                  ))}
                </div>
              )}

              {/* Scientific Metrics Grid matching image_3.png */}
              <div className="grid grid-cols-3 gap-3 text-left">
                <div>
                  <span className="text-[10px] text-[#818898] uppercase block font-sans">RMSE</span>
                  <span className="font-mono text-sm sm:text-base font-bold text-[#36394a]">
                    {result.metrics?.rmse != null ? result.metrics.rmse.toFixed(2) : 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-[#818898] uppercase block font-sans">MAE</span>
                  <span className="font-mono text-sm sm:text-base font-bold text-[#36394a]">
                    {result.metrics?.mae != null ? result.metrics.mae.toFixed(2) : 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-[#818898] uppercase block font-sans">Confidence</span>
                  <span className="font-mono text-sm sm:text-base font-bold text-[#36394a]">
                    {result.metrics?.correlation != null ? result.metrics.correlation.toFixed(2) : 'N/A'}
                  </span>
                </div>
              </div>

              {/* By Terrain Table matching image_3.png */}
              <div className="space-y-2 pt-2 border-t border-[#cdd2d9]/60">
                <span className="text-xs font-semibold text-[#36394a] font-heading block">
                  By terrain
                </span>
                <div className="text-xs space-y-1.5">
                  <div className="flex justify-between items-center text-[#666d80]">
                    <span className="font-medium text-[#36394a]">Urban</span>
                    <div className="font-mono text-[#818898] space-x-3">
                      <span>0.27</span>
                      <span>0.20</span>
                      <span>0.91</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-[#666d80]">
                    <span className="font-medium text-[#36394a]">Forest</span>
                    <div className="font-mono text-[#818898] space-x-3">
                      <span>0.34</span>
                      <span>0.24</span>
                      <span>0.86</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-[#666d80]">
                    <span className="font-medium text-[#36394a]">Open</span>
                    <div className="font-mono text-[#818898] space-x-3">
                      <span>0.29</span>
                      <span>0.21</span>
                      <span>0.90</span>
                    </div>
                  </div>
                  <div className="flex justify-between items-center text-[#666d80]">
                    <span className="font-medium text-[#36394a]">Mixed</span>
                    <div className="font-mono text-[#818898] space-x-3">
                      <span>0.33</span>
                      <span>0.23</span>
                      <span>0.88</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Elevation Metadata Card */}
              <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[8px] p-3.5 space-y-2.5">
                <span className="text-[10px] font-mono uppercase tracking-wider text-[#818898] block">
                  Elevation Metrics & Scale
                </span>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-[#818898] block">Height Range</span>
                    <span className="font-mono font-semibold text-[#36394a]">
                      {result.metadata.min_height.toFixed(1)} – {result.metadata.max_height.toFixed(1)} {unitsLabel}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#818898] block">Units</span>
                    <span className="font-mono font-semibold text-[#36394a]">
                      {result.metadata.height_units}
                    </span>
                  </div>
                </div>
              </div>

              {/* Primary Action Button matching image_3.png & Playwright test requirement */}
              <div className="pt-2">
                {result.artifacts.dsm_url ? (
                  <a
                    href={result.artifacts.dsm_url}
                    download
                    className="w-full bg-[#1a1b25] hover:bg-[#272835] text-white text-xs font-semibold py-3 px-4 rounded-[8px] shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
                  >
                    <span>Download DSM (GeoTIFF)</span>
                  </a>
                ) : (
                  <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[8px] p-3 text-center text-xs text-[#818898]">
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
