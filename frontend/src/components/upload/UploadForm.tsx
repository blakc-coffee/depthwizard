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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.toLowerCase().split('.').pop();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file format (${ext}). Please select a PNG, JPG/JPEG, TIFF, or GeoTIFF image.`;
    }
    return null;
  };

  const handleFileSelect = (file: File) => {
    setErrorMessage(null);
    const err = validateFile(file);
    if (err) {
      setErrorMessage(err);
      setSelectedFile(null);
      return;
    }
    setSelectedFile(file);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleKeyDownDropzone = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement> | React.MouseEvent) => {
    if (e) e.preventDefault();
    setErrorMessage(null);

    if (!selectedFile) {
      setErrorMessage('Please select a satellite or aerial image file before processing.');
      return;
    }

    const validationErr = validateFile(selectedFile);
    if (validationErr) {
      setErrorMessage(validationErr);
      return;
    }

    setSubmitting(true);

    try {
      const response = await createJob(selectedFile);
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
          Upload a supported terrain dataset. DepthWizard will validate it before processing.
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
        <input
          ref={fileInputRef}
          id="file-upload"
          name="file-upload"
          type="file"
          accept=".png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff"
          onChange={handleInputChange}
          disabled={submitting}
          className="sr-only"
        />

        {/* Left Column: Terrain Dataset Workspace */}
        <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-6 space-y-4 w-full">
          <div>
            <h2 className="text-lg font-semibold text-[#36394a] font-heading mb-0.5">
              Terrain dataset
            </h2>
            <p className="text-xs text-[#818898]">
              Accepted: GeoTIFF, DEM, CSV, PNG, JPEG
            </p>
          </div>

          {!selectedFile ? (
            <div
              tabIndex={0}
              role="button"
              aria-label="Upload satellite or aerial image file"
              onKeyDown={handleKeyDownDropzone}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border border-[#cdd2d9] rounded-[12px] p-12 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] bg-white ${
                isDragOver ? 'border-[#5e4cff] bg-[#dfdbff]/20' : 'hover:border-[#5e4cff]'
              }`}
            >
              <h3 className="text-base font-semibold text-[#36394a] font-heading mb-1">
                Drop your file here
              </h3>
              <p className="text-xs text-[#818898] mb-6">
                Drag and drop your image here, or choose a file from your computer
              </p>
              <button
                type="button"
                className="bg-[#5e4cff] hover:bg-[#5e4cff]/90 text-white text-xs font-medium px-6 py-2.5 rounded-[8px] shadow-xs transition-colors pointer-events-none"
              >
                Choose terrain file
              </button>
            </div>
          ) : (
            <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 rounded-lg bg-[#f6f8fa] border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center flex-shrink-0">
                  <svg
                    className="w-6 h-6"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-semibold text-[#36394a] truncate max-w-[200px] sm:max-w-xs">
                      {selectedFile.name}
                    </span>
                    {(() => {
                      const badge = getFileFormatBadge(selectedFile.name);
                      return (
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                            badge.isGeo
                              ? 'bg-[#dfdbff] text-[#5e4cff] border border-[#c8ccf3]'
                              : 'bg-[#f6f8fa] text-[#666d80] border border-[#cdd2d9]'
                          }`}
                        >
                          {badge.label}
                        </span>
                      );
                    })()}
                  </div>
                  <span className="text-xs font-mono text-[#818898]">
                    Size: {formatFileSize(selectedFile.size)}
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-3 self-end sm:self-center">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={submitting}
                  className="text-xs text-[#36394a] hover:text-[#5e4cff] font-medium px-3 py-1.5 rounded-[8px] border border-[#cdd2d9] hover:bg-[#f6f8fa] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
                >
                  Change File
                </button>
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  disabled={submitting}
                  className="text-xs text-red-600 hover:text-red-800 font-medium px-3 py-1.5 rounded-[8px] border border-red-200 hover:bg-red-50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  Remove File
                </button>
              </div>
            </div>
          )}

          <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-4 text-xs text-[#666d80] space-y-1">
            <span className="font-semibold text-[#36394a] block mb-0.5 font-heading">Format Specifications:</span>
            <p>
              • <strong>PNG / JPG:</strong> Standard imagery for relative depth estimation.
            </p>
            <p>
              • <strong>TIFF / GeoTIFF:</strong> Geo-referenced spatial rasters evaluate backend reference elevation anchors for absolute DSM calibration ($m$).
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
              <span className="font-medium text-[#36394a]">File format supported</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">02</span>
              <span className="font-medium text-[#36394a]">Coordinate system detected</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">03</span>
              <span className="font-medium text-[#36394a]">Elevation values readable</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-[#5e4cff] font-semibold mr-3">04</span>
              <span className="font-medium text-[#36394a]">No critical gaps</span>
            </div>
          </div>

          <div className="pt-4 border-t border-[#cdd2d9]">
            <button
              type="submit"
              disabled={!selectedFile || submitting}
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
              <span>Process Image</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
