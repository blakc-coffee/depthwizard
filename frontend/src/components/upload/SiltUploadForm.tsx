import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createSiltJob } from '../../lib/api';
import { getFriendlyErrorMessage } from '../../lib/errors';
import { UploadDropzone } from './UploadDropzone';
import { Badge } from '../common/Badge';

export const SiltUploadForm: React.FC = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (selected: File | null) => {
    setError(null);
    setFile(selected);
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await createSiltJob(file);
      navigate(`/silt-processing/${encodeURIComponent(response.job_id)}`);
    } catch (err) {
      setError(getFriendlyErrorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full space-y-6 flex-1">
      {/* Page Title & Subtitle */}
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading mb-1.5">
          River Silt Estimation
        </h1>
        <p className="text-sm text-slate-500 max-w-2xl">
          Upload an overhead river reach image or satellite capture to estimate suspended sediment concentration (SSC).
        </p>
      </div>

      {/* Two Column Input Workspace — unified with Terrain workspace */}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(320px,360px)] gap-6 items-start w-full">
        {/* Left Column: River Silt Workspace */}
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
          </div>

          <div className="grid grid-cols-1 gap-4">
            <UploadDropzone
              title="Reach Satellite Capture"
              description="Overhead river reach image or satellite capture for sediment concentration estimation."
              badge={<Badge variant="text-only" intent="success">Required</Badge>}
              dotColor="bg-slate-900"
              dropLabel="Drop river reach image here"
              acceptedFormats="Accepted: GeoTIFF, DEM, PNG, JPEG (Up to 100MB)"
              formatHint="or click to browse from device (GeoTIFF / JPG / PNG)"
              ctaLabel="Choose reach file"
              accept="image/png,image/jpeg,.tif,.tiff"
              file={file}
              onFileSelect={handleFile}
              onRemoveFile={() => handleFile(null)}
              disabled={submitting}
            />
          </div>

          {/* Format Specifications footer */}
          <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs text-slate-600 space-y-1.5 shadow-xs">
            <span className="font-semibold text-slate-900 block mb-1 font-heading">Format Specifications:</span>
            <p>
              • <strong>Reach Image:</strong> Multi-spectral or RGB satellite capture (Sentinel-2 / PlanetScope) centered on monitored river reach.
            </p>
          </div>
        </div>

        {/* Right Column: Pre-estimation Checklist & Estimate Button */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-6 w-full lg:min-w-[320px] lg:max-w-[360px] shadow-xs">
          <h2 className="text-base font-semibold text-slate-900 font-heading border-b border-slate-100 pb-3">
            Before processing
          </h2>

          <div className="space-y-4 text-xs">
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">01</span>
              <span className="font-medium text-slate-800">Overhead reach verified</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">02</span>
              <span className="font-medium text-slate-800">Waterway channel identified</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">03</span>
              <span className="font-medium text-slate-800">Minimal cloud obstruction</span>
            </div>
            <div className="flex items-center">
              <span className="font-mono text-slate-900 font-semibold mr-3">04</span>
              <span className="font-medium text-slate-800">Surface reflectance readable</span>
            </div>
          </div>

          {error && (
            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          <div className="pt-2">
            <button
              type="submit"
              disabled={!file || submitting}
              className="w-full bg-[#0F172A] hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold py-3 px-4 rounded-lg shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              <span>{submitting ? 'Estimating Silt Concentration…' : 'Estimate Silt Level'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
