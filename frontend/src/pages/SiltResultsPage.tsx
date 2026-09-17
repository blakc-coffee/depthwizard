import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { DredgingIndicator } from '../components/results/DredgingIndicator';
import { SiltCrossSectionViewer } from '../components/viewer/SiltCrossSectionViewer';
import { Badge } from '../components/common/Badge';
import { getSiltJobResult } from '../lib/api';
import { getFriendlyErrorMessage } from '../lib/errors';
import { SiltJobResult } from '../lib/types';

export const SiltResultsPage = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [result, setResult] = useState<SiltJobResult | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.title = 'DepthWizard | Silt Results';
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

    getSiltJobResult(jobId)
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
    navigate('/silt');
  };

  const isAbsolute = result?.output_type === 'absolute_ssc';

  return (
    <AppShell>
      <div className="w-full flex-1 flex flex-col space-y-6">
        <div className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading">
                River Silt Results
              </h1>
              {result && (
                <>
                  <Badge variant="text-only" intent={isAbsolute ? 'success' : 'warning'}>
                    {isAbsolute ? 'Absolute SSC' : 'Relative Silt Index'}
                  </Badge>
                  <Badge variant="text-only" intent="neutral">
                    Waterway Flood Risk
                  </Badge>
                </>
              )}
            </div>
            <p className="text-sm text-slate-500">
              Estimated suspended sediment concentration and cross-channel deposition profile.
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
              New Silt Upload
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-24 text-sm text-slate-500">
            <svg
              className="animate-spin h-5 w-5 text-slate-900 mr-2"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            Loading silt analysis…
          </div>
        )}

        {error && (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-6 text-sm text-rose-700 max-w-2xl">
            {error}
          </div>
        )}

        {result && (
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-6 items-start">
            {/* Main: channel shape + sediment level is the hero view */}
            <div className="min-h-[520px] xl:min-h-[620px] flex flex-col">
              <SiltCrossSectionViewer
                crossSectionProfile={result.cross_section_profile}
                predictedSscMgL={result.predicted_ssc_mg_l}
              />
            </div>

            {/* Side panel: source photo (reference only) + stats + dredging */}
            <div className="w-full flex flex-col gap-4">
              <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                <h4 className="text-xs font-semibold text-slate-900 font-heading mb-2">Aerial Reach Imagery</h4>
                <img
                  src={result.artifacts.texture_url}
                  alt="Uploaded river reach"
                  className="w-full h-44 rounded-lg border border-slate-200/80 object-cover"
                />
                <span className="text-[11px] text-slate-400 mt-1.5 block">
                  Sentinel-2 L2A Overhead Reach
                </span>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs">
                <h4 className="text-xs font-semibold text-slate-900 font-heading mb-2.5">Concentration Analytics</h4>
                <dl className="space-y-2 text-xs">
                  <div className="flex justify-between items-center pb-1">
                    <dt className="text-slate-500">Predicted SSC</dt>
                    <dd className="font-mono font-bold text-base text-slate-900">
                      {result.predicted_ssc_mg_l.toFixed(1)} mg/L
                    </dd>
                  </div>
                  <div className="flex justify-between items-center">
                    <dt className="text-slate-500">Observation Type</dt>
                    <dd className="font-semibold text-emerald-600">
                      {isAbsolute ? 'Absolute Metric' : 'Relative Index'}
                    </dd>
                  </div>
                  <div className="flex justify-between items-center">
                    <dt className="text-slate-500">Channel Siltation</dt>
                    <dd className="font-mono text-slate-700">Monitored Profile</dd>
                  </div>
                </dl>
              </div>

              <DredgingIndicator
                level={result.dredging_level}
                label={result.dredging_label}
                predictedSscMgL={result.predicted_ssc_mg_l}
              />
            </div>
          </div>
        )}

        {result && result.warnings.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-1.5">
            {result.warnings.map((w, i) => (
              <p key={i} className="text-xs text-amber-800">{w}</p>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
};
