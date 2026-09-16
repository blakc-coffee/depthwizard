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
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-[#36394a] font-heading mb-1.5">
          River Silt Estimation
        </h1>
        <p className="text-sm text-[#666d80] max-w-2xl">
          Upload an overhead river reach image to estimate suspended sediment concentration (SSC).
        </p>
      </div>

      <div className="bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-5 sm:p-6 space-y-5 w-full max-w-2xl">
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
          className={`bg-white border-2 border-dashed rounded-[12px] p-8 flex flex-col items-center justify-center text-center transition-colors cursor-pointer ${
            isDragging ? 'border-[#5e4cff] bg-[#f6f8fa]' : 'border-[#cdd2d9]'
          }`}
        >
          <label className="cursor-pointer flex flex-col items-center">
            <div className="w-10 h-10 rounded-full bg-[#f6f8fa] border border-[#cdd2d9] text-[#5e4cff] flex items-center justify-center mb-2.5">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <span className="text-sm font-medium text-[#36394a]">
              {file ? file.name : 'Drop river reach image (GeoTIFF / JPG / PNG)'}
            </span>
            <span className="text-xs text-[#818898] mt-1">or click to browse</span>
            <input
              type="file"
              accept="image/png,image/jpeg,.tif,.tiff"
              className="hidden"
              onChange={(e) => handleFile(e.target.files?.[0] || null)}
            />
          </label>
        </div>

        {error && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-[8px] px-3 py-2">
            {error}
          </div>
        )}

        <button
          type="button"
          disabled={!file || submitting}
          onClick={handleSubmit}
          className="w-full bg-[#5e4cff] hover:bg-[#4d3ce6] disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2.5 rounded-[8px] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
        >
          {submitting ? 'Uploading…' : 'Estimate Silt Level'}
        </button>
      </div>
    </div>
  );
};
