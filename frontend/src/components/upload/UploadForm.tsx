import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createJob } from '../../lib/api';
import { getFriendlyErrorMessage } from '../../lib/errors';

const ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tif', '.tiff'];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileFormatBadge(filename: string): { label: string; isGeo: boolean } {
  const ext = filename.toLowerCase().split('.').pop() || '';
  if (ext === 'tif' || ext === 'tiff') {
    return { label: 'GeoTIFF / DEM', isGeo: true };
  }
  if (ext === 'png') {
    return { label: 'PNG Image', isGeo: false };
  }
  if (ext === 'jpg' || ext === 'jpeg') {
    return { label: 'JPEG Image', isGeo: false };
  }
  return { label: ext.toUpperCase(), isGeo: false };
}

export const UploadForm = () => {
  const navigate = useNavigate();
  const primaryInputRef = useRef<HTMLInputElement>(null);
  const secondaryInputRef = useRef<HTMLInputElement>(null);

  const [selectedPrimaryFile, setSelectedPrimaryFile] = useState<File | null>(null);
  const [selectedSecondaryFile, setSelectedSecondaryFile] = useState<File | null>(null);

  const [isDragOverPrimary, setIsDragOverPrimary] = useState(false);
  const [isDragOverSecondary, setIsDragOverSecondary] = useState(false);

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

  const handlePrimaryInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handlePrimarySelect(files[0]);
    }
  };

  const handleSecondaryInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleSecondarySelect(files[0]);
    }
  };

  const handleRemovePrimaryFile = () => {
    setSelectedPrimaryFile(null);
    setErrorMessage(null);
    if (primaryInputRef.current) {
      primaryInputRef.current.value = '';
    }
  };

  const handleRemoveSecondaryFile = () => {
    setSelectedSecondaryFile(null);
    if (secondaryInputRef.current) {
      secondaryInputRef.current.value = '';
    }
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
        navigate(`/processing/${encodeURIComponent(response.job_id)}`);
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
          Input Satellite / Aerial Imagery
        </h1>
        <p className="text-sm text-[#666d80]">
          Upload baseline and post-event imagery datasets for 3D elevation estimation and temporal disaster change detection.
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
        {/* Hidden inputs */}
        <input
          ref={primaryInputRef}
          id="file-upload"
          name="file-upload"
          type="file"
          accept=".png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff"
          onChange={handlePrimaryInputChange}
          disabled={submitting}
          className="sr-only"
        />
        <input
          ref={secondaryInputRef}
          id="file-upload-secondary"
          name="file-upload-secondary"
          type="file"
          accept=".png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff"
          onChange={handleSecondaryInputChange}
          disabled={submitting}
          className="sr-only"
        />

        {/* Left Column: Dual Imagery Workspaces */}
        <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-5 sm:p-6 space-y-5 w-full">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#cdd2d9]/70 pb-3">
            <div>
              <h2 className="text-lg font-semibold text-[#36394a] font-heading mb-0.5">
                Imagery Inputs
              </h2>
              <p className="text-xs text-[#818898]">
                Accepted: GeoTIFF, DEM, PNG, JPEG (Up to 100MB per file)
              </p>
            </div>
            {selectedSecondaryFile && (
              <span className="text-xs font-semibold text-[#5e4cff] bg-[#dfdbff] px-2.5 py-1 rounded-full border border-[#c8ccf3]">
                Dual Comparison Mode Active
              </span>
            )}
          </div>

          {/* Dual Dropzones: Grid layout */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {/* Input 1: Primary (Baseline) */}
            <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-[#5e4cff]" />
                    <span className="text-xs font-semibold text-[#36394a] uppercase tracking-wide">
                      Input 1 · Baseline
                    </span>
                  </div>
                  <span className="text-[11px] font-semibold text-[#5e4cff] bg-[#dfdbff] px-2 py-0.5 rounded-full border border-[#c8ccf3]">
                    Required
                  </span>
                </div>
                <p className="text-xs text-[#818898] mb-3">
                  Pre-disaster aerial or satellite capture for baseline topography.
                </p>
              </div>

              {!selectedPrimaryFile ? (
                <div
                  tabIndex={0}
                  role="button"
                  aria-label="Upload satellite or aerial image file"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      primaryInputRef.current?.click();
                    }
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverPrimary(true);
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverPrimary(false);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverPrimary(false);
                    const files = e.dataTransfer.files;
                    if (files && files.length > 0) handlePrimarySelect(files[0]);
                  }}
                  onClick={() => primaryInputRef.current?.click()}
                  className={`border border-dashed border-[#cdd2d9] rounded-[10px] p-6 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] bg-[#fdfdfd] flex flex-col items-center justify-center min-h-[190px] ${
                    isDragOverPrimary ? 'border-[#5e4cff] bg-[#dfdbff]/20' : 'hover:border-[#5e4cff] hover:bg-[#f6f8fa]'
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-[#f6f8fa] border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center mb-2.5">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <h3 className="text-sm font-semibold text-[#36394a] font-heading mb-0.5">
                    Drop your image here
                  </h3>
                  <p className="text-[11px] text-[#818898] mb-3">
                    Drag and drop your image here, or choose a file
                  </p>
                  <button
                    type="button"
                    className="bg-[#5e4cff] hover:bg-[#5e4cff]/90 text-white text-xs font-medium px-4 py-1.5 rounded-[8px] shadow-2xs transition-colors pointer-events-none"
                  >
                    Choose baseline file
                  </button>
                </div>
              ) : (
                <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[10px] p-3.5 flex flex-col justify-between gap-3 min-h-[190px]">
                  <div className="flex items-start space-x-3">
                    <div className="w-10 h-10 rounded-lg bg-white border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center flex-shrink-0 mt-0.5">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-[#36394a] truncate" title={selectedPrimaryFile.name}>
                        {selectedPrimaryFile.name}
                      </p>
                      <div className="flex items-center space-x-1.5 mt-1">
                        {(() => {
                          const badge = getFileFormatBadge(selectedPrimaryFile.name);
                          return (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                                badge.isGeo
                                  ? 'bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]'
                                  : 'bg-white text-[#666d80] border border-[#cdd2d9]'
                              }`}
                            >
                              {badge.label}
                            </span>
                          );
                        })()}
                        <span className="text-[11px] font-mono text-[#818898]">
                          Size: {formatFileSize(selectedPrimaryFile.size)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 pt-2 border-t border-[#cdd2d9]/60">
                    <button
                      type="button"
                      onClick={() => primaryInputRef.current?.click()}
                      disabled={submitting}
                      className="flex-1 text-xs text-[#36394a] hover:text-[#5e4cff] font-medium py-1.5 rounded-[8px] border border-[#cdd2d9] bg-white hover:bg-[#f6f8fa] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
                    >
                      Change
                    </button>
                    <button
                      type="button"
                      onClick={handleRemovePrimaryFile}
                      disabled={submitting}
                      className="flex-1 text-xs text-red-600 hover:text-red-800 font-medium py-1.5 rounded-[8px] border border-red-200 bg-white hover:bg-red-50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
                    >
                      Remove File
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Input 2: Secondary (Post-Disaster / Event) */}
            <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    <span className="text-xs font-semibold text-[#36394a] uppercase tracking-wide">
                      Input 2 · Event / Post
                    </span>
                  </div>
                  <span className="text-[11px] font-medium text-[#666d80] bg-[#e2e4e9] px-2 py-0.5 rounded-full border border-[#cdd2d9]">
                    Optional
                  </span>
                </div>
                <p className="text-xs text-[#818898] mb-3">
                  Post-disaster capture of same location for difference & damage heatmap.
                </p>
              </div>

              {!selectedSecondaryFile ? (
                <div
                  tabIndex={0}
                  role="button"
                  aria-label="Upload secondary event image file"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      secondaryInputRef.current?.click();
                    }
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverSecondary(true);
                  }}
                  onDragLeave={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverSecondary(false);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setIsDragOverSecondary(false);
                    const files = e.dataTransfer.files;
                    if (files && files.length > 0) handleSecondarySelect(files[0]);
                  }}
                  onClick={() => secondaryInputRef.current?.click()}
                  className={`border border-dashed border-[#cdd2d9] rounded-[10px] p-6 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] bg-[#fdfdfd] flex flex-col items-center justify-center min-h-[190px] ${
                    isDragOverSecondary ? 'border-amber-500 bg-amber-50/30' : 'hover:border-amber-400 hover:bg-[#f6f8fa]'
                  }`}
                >
                  <div className="w-10 h-10 rounded-full bg-[#f6f8fa] border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center mb-2.5">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                  </div>
                  <h3 className="text-sm font-semibold text-[#36394a] font-heading mb-0.5">
                    Drop event image (optional)
                  </h3>
                  <p className="text-[11px] text-[#818898] mb-3">
                    Drag and drop post-disaster image, or choose a file
                  </p>
                  <button
                    type="button"
                    className="bg-white hover:bg-[#f6f8fa] text-[#36394a] border border-[#cdd2d9] text-xs font-medium px-4 py-1.5 rounded-[8px] shadow-2xs transition-colors pointer-events-none"
                  >
                    Choose event file
                  </button>
                </div>
              ) : (
                <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[10px] p-3.5 flex flex-col justify-between gap-3 min-h-[190px]">
                  <div className="flex items-start space-x-3">
                    <div className="w-10 h-10 rounded-lg bg-white border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center flex-shrink-0 mt-0.5">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-[#36394a] truncate" title={selectedSecondaryFile.name}>
                        {selectedSecondaryFile.name}
                      </p>
                      <div className="flex items-center space-x-1.5 mt-1">
                        {(() => {
                          const badge = getFileFormatBadge(selectedSecondaryFile.name);
                          return (
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                                badge.isGeo
                                  ? 'bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]'
                                  : 'bg-white text-[#666d80] border border-[#cdd2d9]'
                              }`}
                            >
                              {badge.label}
                            </span>
                          );
                        })()}
                        <span className="text-[11px] font-mono text-[#818898]">
                          Size: {formatFileSize(selectedSecondaryFile.size)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 pt-2 border-t border-[#cdd2d9]/60">
                    <button
                      type="button"
                      onClick={() => secondaryInputRef.current?.click()}
                      disabled={submitting}
                      className="flex-1 text-xs text-[#36394a] hover:text-[#5e4cff] font-medium py-1.5 rounded-[8px] border border-[#cdd2d9] bg-white hover:bg-[#f6f8fa] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
                    >
                      Change
                    </button>
                    <button
                      type="button"
                      onClick={handleRemoveSecondaryFile}
                      disabled={submitting}
                      className="flex-1 text-xs text-red-600 hover:text-red-800 font-medium py-1.5 rounded-[8px] border border-red-200 bg-white hover:bg-red-50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Format specifications note */}
          <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-4 text-xs text-[#666d80] space-y-1.5">
            <span className="font-semibold text-[#36394a] block mb-1 font-heading">Format Specifications:</span>
            <p>
              • <strong>Primary Image (Baseline):</strong> Ground elevation reference for 3D reconstruction and calibration ($m$).
            </p>
            <p>
              • <strong>Secondary Image (Event - Optional):</strong> Post-disaster comparison layer enabling 3-way toggle and difference heatmap generation.
            </p>
          </div>
        </div>

        {/* Right Column: Before Processing Card */}
        <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-6 space-y-6 w-full lg:min-w-[320px] lg:max-w-[360px]">
          <h2 className="text-base font-semibold text-[#36394a] font-heading border-b border-[#cdd2d9] pb-3">
            Before processing
          </h2>

          <div className="space-y-4 text-xs">
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">01</span>
              <span className="font-medium text-[#36394a]">Primary baseline verified</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">02</span>
              <span className="font-medium text-[#36394a]">
                {selectedSecondaryFile ? 'Dual temporal alignment detected' : 'Single capture mode (no event)'}
              </span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">03</span>
              <span className="font-medium text-[#36394a]">Elevation values readable</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">04</span>
              <span className="font-medium text-[#36394a]">No critical raster gaps</span>
            </div>
          </div>

          <div className="pt-4 border-t border-[#cdd2d9]">
            <button
              type="submit"
              disabled={!selectedPrimaryFile || submitting}
              className="w-full bg-[#1a1b25] hover:bg-[#272835] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold py-3 px-4 rounded-[8px] transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
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
              <span>{selectedSecondaryFile ? 'Process Both Images' : 'Process Image'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
