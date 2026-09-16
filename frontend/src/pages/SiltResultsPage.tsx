import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { DredgingIndicator } from '../components/results/DredgingIndicator';
import { SiltCrossSectionViewer } from '../components/viewer/SiltCrossSectionViewer';
import { SiltHeatmapViewer } from '../components/viewer/SiltHeatmapViewer';
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
        <div className="w-full flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#cdd2d9] flex-shrink-0">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-3 mb-1">
              <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#36394a] font-heading">
                River Silt Results
              </h1>
              {result && (
                <span
                  className={`text-xs px-3 py-1 rounded-full font-medium ${
                    isAbsolute
                      ? 'bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]'
                      : 'bg-amber-50 text-amber-800 border border-amber-200'
                  }`}
                >
                  {isAbsolute ? 'Absolute SSC' : 'Relative Silt Index'}
                </span>
              )}
            </div>
            <p className="text-sm text-[#666d80]">Estimated suspended sediment concentration for the uploaded reach.</p>
          </div>

          <div className="flex items-center space-x-3 self-start sm:self-center">
            <span className="text-xs font-mono text-[#818898] hidden sm:inline-block">Job: {jobId || 'Unknown'}</span>
            <button
              type="button"
              onClick={handleReturnToWorkspace}
              className="text-xs bg-white hover:bg-[#f6f8fa] border border-[#cdd2d9] text-[#36394a] font-medium px-4 py-2 rounded-[8px] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] flex-shrink-0"
            >
              New Upload
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-24 text-sm text-[#666d80]">Loading results…</div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-[12px] p-6 text-sm text-red-700 max-w-2xl">
            {error}
          </div>
        )}

        {result && (
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-6 items-start">
            <div className="flex flex-col gap-6">
              <SiltHeatmapViewer
                sourceImageUrl={result.artifacts.texture_url}
                heatmapUrl={result.artifacts.heatmap_url}
                outputType={result.output_type}
                meanSscMgL={result.predicted_ssc_mg_l}
                peakSscMgL={result.predicted_ssc_mg_l}
                confidence={null}
              />
              <SiltCrossSectionViewer
                crossSectionProfile={result.cross_section_profile}
                predictedSscMgL={result.predicted_ssc_mg_l}
              />
            </div>
            <div className="w-full xl:w-80 flex-shrink-0">
              <DredgingIndicator
                level={result.dredging_level}
                label={result.dredging_label}
                predictedSscMgL={result.predicted_ssc_mg_l}
              />
            </div>
          </div>
        )}

        {result && result.warnings.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-[12px] p-4 space-y-1.5">
            {result.warnings.map((w, i) => (
              <p key={i} className="text-xs text-amber-800">{w}</p>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
};
