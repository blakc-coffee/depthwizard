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
    return { label: 'TIFF / GeoTIFF', isGeo: true };
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

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
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
    <div className="w-full max-w-3xl mx-auto space-y-6">
      <div className="bg-[#FDFCF8] border border-gray-200 rounded-xl p-6 sm:p-8 shadow-sm">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 mb-1.5">
            Input Satellite / Aerial Imagery
          </h1>
          <p className="text-sm text-gray-600">
            Upload an image to initiate single-view depth estimation, reference calibration, and 3D terrain reconstruction.
          </p>
        </div>

        {errorMessage && (
          <div
            role="alert"
            aria-live="polite"
            className="mb-6 bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] text-sm rounded-md p-4 flex items-start space-x-3"
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
              <span className="font-medium">Upload Error: </span>
              <span>{errorMessage}</span>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
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
              className={`border-2 border-dashed rounded-xl p-8 sm:p-12 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600 ${
                isDragOver
                  ? 'border-purple-600 bg-purple-50/40'
                  : 'border-gray-300 hover:border-purple-500 bg-[#FDFCF8]'
              }`}
            >
              <div className="w-14 h-14 rounded-full bg-[#ECE9DD] text-purple-800 mx-auto mb-4 flex items-center justify-center">
                <svg
                  className="w-7 h-7"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </div>
              <p className="text-base font-medium text-gray-900 mb-1">
                Drag and drop your image here, or{' '}
                <label
                  htmlFor="file-upload"
                  className="text-purple-700 underline font-semibold hover:text-purple-900 cursor-pointer"
                  onClick={(e) => e.stopPropagation()}
                >
                  browse files
                </label>
              </p>
              <p className="text-xs text-gray-500 font-sans">
                Supports PNG, JPG/JPEG, TIFF, and GeoTIFF
              </p>
            </div>
          ) : (
            <div className="bg-[#FDFCF8] border border-gray-300 rounded-xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 rounded-lg bg-[#ECE9DD] text-purple-900 flex items-center justify-center flex-shrink-0">
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
                    <span className="text-sm font-semibold text-gray-900 truncate max-w-[220px] sm:max-w-xs">
                      {selectedFile.name}
                    </span>
                    {(() => {
                      const badge = getFileFormatBadge(selectedFile.name);
                      return (
                        <span
                          className={`text-xs px-2 py-0.5 rounded font-mono font-medium ${
                            badge.isGeo
                              ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                              : 'bg-[#ECE9DD] text-gray-800'
                          }`}
                        >
                          {badge.label}
                        </span>
                      );
                    })()}
                  </div>
                  <span className="text-xs font-mono text-gray-500">
                    Size: {formatFileSize(selectedFile.size)}
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-3 self-end sm:self-center">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={submitting}
                  className="text-xs text-purple-700 hover:text-purple-900 font-medium px-3 py-1.5 rounded border border-gray-300 hover:bg-[#ECE9DD] transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600"
                >
                  Change File
                </button>
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  disabled={submitting}
                  className="text-xs text-red-600 hover:text-red-800 font-medium px-3 py-1.5 rounded border border-red-200 hover:bg-red-50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  Remove File
                </button>
              </div>
            </div>
          )}

          <div className="bg-[#ECE9DD]/60 border border-[#ECE9DD] rounded-lg p-4 text-xs text-gray-700 space-y-1">
            <span className="font-semibold text-gray-900 block mb-0.5">Format Specifications:</span>
            <p>
              • <strong>PNG / JPG:</strong> Standard imagery for relative depth estimation.
            </p>
            <p>
              • <strong>TIFF / GeoTIFF:</strong> Geo-referenced spatial rasters evaluate backend reference elevation anchors for absolute DSM calibration ($m$).
            </p>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={!selectedFile || submitting}
              className="w-full bg-purple-700 hover:bg-purple-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 px-6 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-600 focus:ring-offset-2 transition-colors flex items-center justify-center space-x-2 text-base"
            >
              {submitting && (
                <svg
                  className="animate-spin h-5 w-5 text-white"
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
        </form>
      </div>
    </div>
  );
};
