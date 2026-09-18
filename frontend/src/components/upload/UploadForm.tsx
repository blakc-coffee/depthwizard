import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createJob } from '../../lib/api';
import { getFriendlyErrorMessage } from '../../lib/errors';
import { UploadDropzone } from './UploadDropzone';
import { Badge } from '../common/Badge';

const ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tif', '.tiff'];

export const UploadForm = () => {
  const navigate = useNavigate();

  // Single-file DSM upload is the default; comparison mode is opt-in.
  const [comparisonMode, setComparisonMode] = useState(false);
  const singleFileOnly = !comparisonMode;

  const [selectedPrimaryFile, setSelectedPrimaryFile] = useState<File | null>(null);
  const [selectedSecondaryFile, setSelectedSecondaryFile] = useState<File | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.toLowerCase().split('.').pop();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file format (${ext}). Please select a PNG, JPG/JPEG, TIFF, or GeoTIFF image.`;
    }
    return null;
  };

  const handlePrimarySelect = (file: File) => {
    setErrorMessage(null);
    const err = validateFile(file);
    if (err) {
      setErrorMessage(`Primary Image: ${err}`);
      setSelectedPrimaryFile(null);
      return;
    }
    setSelectedPrimaryFile(file);
  };

  const handleSecondarySelect = (file: File) => {
    setErrorMessage(null);
    const err = validateFile(file);
    if (err) {
      setErrorMessage(`Secondary Image: ${err}`);
      setSelectedSecondaryFile(null);
      return;
    }
    setSelectedSecondaryFile(file);
  };

  const handleRemovePrimaryFile = () => {
    setSelectedPrimaryFile(null);
    setErrorMessage(null);
  };

  const handleRemoveSecondaryFile = () => {
    setSelectedSecondaryFile(null);
  };

  const handleToggleComparisonMode = () => {
    if (comparisonMode) {
      handleRemoveSecondaryFile();
    }
    setComparisonMode((prev) => !prev);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement> | React.MouseEvent) => {
    if (e) e.preventDefault();
    setErrorMessage(null);

    if (!selectedPrimaryFile) {
      setErrorMessage('Please select a primary satellite or aerial baseline image before processing.');
      return;
    }

    const validationErr = validateFile(selectedPrimaryFile);
    if (validationErr) {
      setErrorMessage(validationErr);
      return;
    }

    if (selectedSecondaryFile) {
      const secErr = validateFile(selectedSecondaryFile);
      if (secErr) {
        setErrorMessage(secErr);
        return;
      }
    }

    setSubmitting(true);

    try {
      const response = await createJob(selectedPrimaryFile, selectedSecondaryFile);
      if (response && response.job_id) {
        if (typeof window !== 'undefined') {
          const isComparison = Boolean(selectedSecondaryFile || response.compare_id || response.secondary_job_id);
          sessionStorage.setItem(`depthwizard_is_comparison_${response.job_id}`, isComparison ? 'true' : 'false');
          if (response.compare_id) {
            sessionStorage.setItem(`depthwizard_compare_id_${response.job_id}`, response.compare_id);
          }
        }
        // Query params are the real (compare/secondary) source of truth for
        // ResultsPage's polling — sessionStorage above is only a same-tab
        // fallback for tab-visibility if someone navigates back without them.
        const params = new URLSearchParams();
        if (response.compare_id) params.set('compare', response.compare_id);
        if (response.secondary_job_id) params.set('secondary', response.secondary_job_id);
        const query = params.toString();
        navigate(`/processing/${encodeURIComponent(response.job_id)}${query ? `?${query}` : ''}`);
      } else {
        setErrorMessage('Failed to create processing job. Unexpected server response.');
        setSubmitting(false);
      }
    } catch (err) {
      setErrorMessage(getFriendlyErrorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full space-y-6 flex-1">
      {/* Page Title & Subtitle */}
      <div className="mb-6">
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#36394a] font-heading mb-2">
          {singleFileOnly ? 'Upload DSM / Terrain Image' : 'Input Satellite / Aerial Imagery'}
        </h1>
        <p className="text-sm text-[#666d80]">
          {singleFileOnly
            ? 'Upload a single satellite/aerial image or GeoTIFF DSM for 3D elevation estimation.'
            : 'Upload baseline and post-event imagery datasets for 3D elevation estimation and temporal disaster change detection.'}
        </p>
      </div>

      {errorMessage && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-6 bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] text-xs rounded-[12px] p-4 flex items-start space-x-3"
        >
          <svg
            className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5"
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
          <div className="flex-1">
            <span className="font-semibold">Upload Error: </span>
            <span>{errorMessage}</span>
          </div>
        </div>
      )}

      {/* Two Column Input Workspace */}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,360px)] gap-6 items-start w-full">
        {/* Left Column: Dual Imagery Workspaces */}
        <div className="bg-[#f8fafc] border border-slate-200 rounded-2xl p-5 sm:p-6 space-y-5 w-full">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 font-heading mb-0.5">
                Imagery Inputs
              </h2>
              <p className="text-xs text-slate-500">
                Accepted: GeoTIFF, DEM, PNG, JPEG (Up to 100MB per file)
              </p>
            </div>
            <div className="flex items-center gap-2">
              {!singleFileOnly && selectedSecondaryFile && (
                <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                  Dual Comparison Mode Active
                </span>
              )}
              <button
                type="button"
                onClick={handleToggleComparisonMode}
                disabled={submitting}
                className="text-xs font-medium text-slate-700 hover:text-slate-900 border border-slate-200 bg-white hover:bg-slate-50 px-3 py-1.5 rounded-lg shadow-2xs transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-40"
              >
                {comparisonMode ? '− Remove comparison image' : '+ Add comparison image'}
              </button>
            </div>
          </div>

          {/* Dropzones: single column in single-file mode, dual grid otherwise */}
          <div className={`grid grid-cols-1 gap-4 ${singleFileOnly ? '' : 'xl:grid-cols-2'}`}>
            {/* Input 1: Primary (Baseline / DSM) */}
            <UploadDropzone
              title={singleFileOnly ? 'DSM / Terrain File' : 'Input 1 · Baseline'}
              description={
                singleFileOnly
                  ? 'Single GeoTIFF DSM or aerial/satellite image for 3D elevation reconstruction.'
                  : 'Pre-disaster aerial or satellite capture for baseline topography.'
              }
              badge={<Badge variant="text-only" intent="success">Required</Badge>}
              dotColor="bg-slate-900"
              dropLabel="Drop your image here"
              acceptedFormats="Accepted: GeoTIFF, DEM, PNG, JPEG (Up to 100MB)"
              formatHint="Drag and drop your image here, or choose a file"
              ctaLabel="Choose baseline file"
              accept=".png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff"
              file={selectedPrimaryFile}
              onFileSelect={handlePrimarySelect}
              onRemoveFile={handleRemovePrimaryFile}
              disabled={submitting}
            />

            {/* Input 2: Secondary (Post-Disaster / Event) */}
            {!singleFileOnly && (
              <UploadDropzone
                title="Input 2 · Event / Post"
                description="Post-disaster capture of same location for difference & damage heatmap."
                badge={<Badge variant="text-only" intent="neutral">Optional</Badge>}
                dotColor="bg-amber-500"
                dropLabel="Drop event image (optional)"
                acceptedFormats="Accepted: GeoTIFF, DEM, PNG, JPEG (Up to 100MB)"
                formatHint="Drag and drop post-disaster image, or choose a file"
                ctaLabel="Choose event file"
                accept=".png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff"
                file={selectedSecondaryFile}
                onFileSelect={handleSecondarySelect}
                onRemoveFile={handleRemoveSecondaryFile}
                disabled={submitting}
              />
            )}
          </div>

          {/* Format specifications note */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs text-slate-600 space-y-1.5 shadow-xs">
            <span className="font-semibold text-slate-900 block mb-1 font-heading">Format Specifications:</span>
            <p>
              • <strong>{singleFileOnly ? 'DSM / Image:' : 'Primary Image (Baseline):'}</strong> Ground elevation reference for 3D reconstruction and calibration ($m$).
            </p>
            {!singleFileOnly && (
              <p>
                • <strong>Secondary Image (Event - Optional):</strong> Post-disaster comparison layer enabling 3-way toggle and difference heatmap generation.
              </p>
            )}
          </div>
        </div>

        {/* Right Column: Before Processing Card */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-6 w-full lg:min-w-[320px] lg:max-w-[360px] shadow-xs">
          <h2 className="text-base font-semibold text-slate-900 font-heading border-b border-slate-100 pb-3">
            Before processing
          </h2>

          <div className="space-y-4 text-xs">
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">01</span>
              <span className="font-medium text-slate-800">Primary baseline verified</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">02</span>
              <span className="font-medium text-slate-800">
                {selectedSecondaryFile ? 'Dual temporal alignment detected' : 'Single capture mode (no event)'}
              </span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">03</span>
              <span className="font-medium text-slate-800">Elevation values readable</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">04</span>
              <span className="font-medium text-slate-800">No critical raster gaps</span>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100">
            <button
              type="submit"
              disabled={!selectedPrimaryFile || submitting}
              className="w-full bg-[#0F172A] hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold py-3 px-4 rounded-lg shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              {submitting && (
                <svg
                  className="animate-spin h-4 w-4 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
              )}
              <span>{singleFileOnly ? 'Process DSM' : selectedSecondaryFile ? 'Process Both Images' : 'Process Image'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
