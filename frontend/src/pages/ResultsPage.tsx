import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { TerrainViewer } from '../components/viewer/TerrainViewer';
import { getJobResult } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { JobResult } from '../lib/types';

export const ResultsPage = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [result, setResult] = useState<JobResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

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
      <div className="py-4 sm:py-6 space-y-6 max-w-full overflow-hidden">
        {/* Header Title */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-200 pb-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-gray-900">
                Terrain Reconstruction Results
              </h1>
              {result && (
                <span
                  className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${
                    isAbsolute
                      ? 'bg-purple-100 text-purple-900 border-purple-200'
                      : 'bg-[#ECE9DD] text-gray-800 border-gray-300'
                  }`}
                >
                  {isAbsolute ? 'Absolute DSM' : 'Relative DSM'}
                </span>
              )}
            </div>
            <p className="text-xs font-mono text-gray-500 break-all">
              Job Reference: {jobId || 'Unknown'}
            </p>
          </div>

          <button
            type="button"
            onClick={handleReturnToWorkspace}
            className="self-start sm:self-center text-xs bg-[#FDFCF8] hover:bg-[#ECE9DD] border border-gray-300 text-gray-800 font-medium px-3.5 py-2 rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600 flex-shrink-0"
          >
            New Terrain Job
          </button>
        </div>

        {/* Loading Skeleton */}
        {loading && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[600px]">
            <div className="lg:col-span-4 bg-[#FDFCF8] border border-gray-200 rounded-xl p-6 space-y-6 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/2 mb-4" />
              <div className="h-44 bg-[#ECE9DD] rounded-lg" />
              <div className="h-44 bg-[#ECE9DD] rounded-lg" />
              <div className="space-y-2">
                <div className="h-3 bg-gray-200 rounded w-3/4" />
                <div className="h-3 bg-gray-200 rounded w-2/3" />
              </div>
            </div>
            <div className="lg:col-span-8 bg-[#FDFCF8] border border-gray-200 rounded-xl p-6 min-h-[500px] flex items-center justify-center animate-pulse">
              <span className="text-sm text-gray-500">Loading 3D visualization artifacts…</span>
            </div>
          </div>
        )}

        {/* Error State */}
        {error && !loading && (
          <div className="max-w-2xl mx-auto bg-[#FEE2E2] border border-[#FCA5A5] rounded-xl p-6 space-y-4 text-left">
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
                <h2 className="text-base font-semibold mb-1">Results Unavailable</h2>
                <p className="text-sm">{error}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="bg-purple-700 hover:bg-purple-800 text-white text-xs font-medium px-4 py-2 rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600"
            >
              Return to Workspace
            </button>
          </div>
        )}

        {/* Completed Results View */}
        {result && !loading && !error && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Summary Panel */}
            <div className="lg:col-span-4 bg-[#FDFCF8] border border-gray-200 rounded-xl p-4 sm:p-6 shadow-sm space-y-6 w-full max-w-full overflow-hidden">
              {/* Warnings Banner */}
              {result.warnings && result.warnings.length > 0 && (
                <div
                  role="alert"
                  aria-live="polite"
                  className="bg-amber-50 border border-amber-300 rounded-lg p-3.5 space-y-1.5 text-xs text-amber-900"
                >
                  <div className="flex items-center space-x-1.5 font-semibold">
                    <svg className="w-4 h-4 text-amber-700 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>Calibration Notice</span>
                  </div>
                  {result.warnings.map((warn, idx) => (
                    <p key={idx} className="leading-relaxed break-words">
                      {warn}
                    </p>
                  ))}
                </div>
              )}

              {/* Elevation Metadata Card */}
              <div className="bg-[#ECE9DD]/40 border border-[#ECE9DD] rounded-lg p-4 space-y-3">
                <span className="text-xs font-mono uppercase tracking-wider text-gray-500 block">
                  Elevation Metrics & Scale
                </span>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-xs text-gray-500 block">Height Range</span>
                    <span className="font-mono text-xs sm:text-sm font-semibold text-gray-900 tabular-nums break-words">
                      {result.metadata.min_height.toFixed(1)} – {result.metadata.max_height.toFixed(1)} {unitsLabel}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500 block">Height Units</span>
                    <span className="font-mono text-xs sm:text-sm font-semibold text-gray-900">
                      {result.metadata.height_units}
                    </span>
                  </div>
                </div>

                <div className="pt-2 border-t border-gray-200/60 grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="text-gray-500 block">Resolution</span>
                    <span className="font-mono text-gray-800">
                      {result.metadata.width} × {result.metadata.height} px
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 block">Output Type</span>
                    <span className="font-mono text-gray-800">{result.output_type}</span>
                  </div>
                </div>
              </div>

              {/* Scientific Metrics Card */}
              <div className="border border-gray-200 rounded-lg p-4 space-y-2.5">
                <span className="text-xs font-mono uppercase tracking-wider text-gray-500 block">
                  Validation Metrics
                </span>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-[#ECE9DD]/40 p-2 rounded">
                    <span className="text-[10px] text-gray-500 block uppercase">RMSE</span>
                    <span className="font-mono text-xs font-bold text-gray-900">
                      {result.metrics?.rmse != null ? result.metrics.rmse.toFixed(2) : 'N/A'}
                    </span>
                  </div>
                  <div className="bg-[#ECE9DD]/40 p-2 rounded">
                    <span className="text-[10px] text-gray-500 block uppercase">MAE</span>
                    <span className="font-mono text-xs font-bold text-gray-900">
                      {result.metrics?.mae != null ? result.metrics.mae.toFixed(2) : 'N/A'}
                    </span>
                  </div>
                  <div className="bg-[#ECE9DD]/40 p-2 rounded">
                    <span className="text-[10px] text-gray-500 block uppercase">Corr</span>
                    <span className="font-mono text-xs font-bold text-gray-900">
                      {result.metrics?.correlation != null ? result.metrics.correlation.toFixed(2) : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Artifact Image Previews */}
              <div className="space-y-4">
                <div>
                  <span className="text-xs font-medium text-gray-700 block mb-1.5">
                    Original RGB Texture
                  </span>
                  <div className="bg-[#ECE9DD] rounded-lg overflow-hidden border border-gray-200 max-h-48 flex items-center justify-center">
                    <img
                      src={result.artifacts.texture_url}
                      alt="Original RGB Texture Preview"
                      className="w-full h-full object-cover"
                    />
                  </div>
                </div>

                <div>
                  <span className="text-xs font-medium text-gray-700 block mb-1.5">
                    Decoded Heightmap (8-bit LA)
                  </span>
                  <div className="bg-[#ECE9DD] rounded-lg overflow-hidden border border-gray-200 max-h-48 flex items-center justify-center">
                    <img
                      src={result.artifacts.heightmap_url}
                      alt="Decoded Heightmap Preview"
                      className="w-full h-full object-cover"
                    />
                  </div>
                </div>
              </div>

              {/* Downloads Section */}
              <div className="pt-2 border-t border-gray-200 space-y-2">
                <span className="text-xs font-semibold text-gray-900 block">Export Artifacts</span>

                {result.artifacts.dsm_url ? (
                  <a
                    href={result.artifacts.dsm_url}
                    download
                    className="w-full bg-purple-700 hover:bg-purple-800 text-white text-xs font-medium py-2.5 px-4 rounded-md shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-purple-600"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    <span>Download DSM (GeoTIFF)</span>
                  </a>
                ) : (
                  <div className="bg-gray-100 border border-gray-200 rounded-md p-3 text-center text-xs text-gray-500">
                    DSM GeoTIFF unavailable
                  </div>
                )}
              </div>
            </div>

            {/* Right 3D Terrain Viewer Section */}
            <div className="lg:col-span-8 h-[480px] sm:h-[620px] w-full max-w-full overflow-hidden">
              <TerrainViewer
                heightmapUrl={result.artifacts.heightmap_url}
                textureUrl={result.artifacts.texture_url}
                confidenceMapUrl={result.artifacts.confidence_map_url}
                outputType={result.output_type}
                maxHeight={result.metadata.max_height}
              />
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
