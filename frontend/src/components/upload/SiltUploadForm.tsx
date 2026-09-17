import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createSiltJob } from '../../lib/api';
import { getFriendlyErrorMessage } from '../../lib/errors';

// Simpler than UploadForm.tsx (terrain) by design — the silt use case has
// no secondary-file/compare flow yet (docs/phase_river_silt.md §4's mockup
// shows a single drop zone + optional gauge-station field, the latter not
// wired to anything on the backend yet since Chunk 3's gauge-anchor fusion
// doesn't exist — omitted here rather than added as dead UI).
export const SiltUploadForm = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (selected: File | null) => {
    setError(null);
    setFile(selected);
  };

  const handleSubmit = async () => {
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
      <div className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-slate-900 font-heading mb-1.5">
          River Silt Estimation
        </h1>
        <p className="text-sm text-slate-500 max-w-2xl">
          Upload an overhead river reach image or satellite capture to estimate suspended sediment concentration (SSC).
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 space-y-6 w-full max-w-2xl shadow-xs">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) handleFile(dropped);
          }}
          className={`border-2 border-dashed rounded-xl p-8 sm:p-10 flex flex-col items-center justify-center text-center transition-colors cursor-pointer ${
            isDragging
              ? 'border-slate-900 bg-slate-50'
              : 'border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50'
          }`}
        >
          <label className="cursor-pointer flex flex-col items-center">
            <div className="w-12 h-12 rounded-full bg-white border border-slate-200 text-slate-700 flex items-center justify-center mb-3 shadow-2xs">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <span className="text-sm font-semibold text-slate-900">
              {file ? file.name : 'Drop river reach image here'}
            </span>
            <span className="text-xs text-slate-500 mt-1">or click to browse from device (GeoTIFF / JPG / PNG)</span>
            <input
              type="file"
              accept="image/png,image/jpeg,.tif,.tiff"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>

        {error && (
          <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="button"
          disabled={!file || submitting}
          onClick={handleSubmit}
          className="w-full bg-[#0F172A] hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-3 rounded-xl shadow-xs transition-colors flex items-center justify-center space-x-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          <span>{submitting ? 'Estimating Sediment Concentration…' : 'Estimate Silt Level'}</span>
        </button>
      </div>
    </div>
  );
};
