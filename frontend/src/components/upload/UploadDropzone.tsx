import React, { useRef, useState } from 'react';

export interface UploadDropzoneProps {
  title?: string;
  description?: string;
  dropLabel: string;
  acceptedFormats?: string;
  formatHint?: string;
  ctaLabel?: string;
  badge?: React.ReactNode;
  dotColor?: string;
  accept?: string;
  file?: File | null;
  onFileSelect: (file: File) => void;
  onRemoveFile?: () => void;
  disabled?: boolean;
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

const getFileFormatBadge = (filename: string): { label: string; isGeo: boolean } => {
  const ext = filename.toLowerCase().split('.').pop() || '';
  if (ext === 'tif' || ext === 'tiff') {
    return { label: 'GeoTIFF / DEM', isGeo: true };
  }
  return { label: ext.toUpperCase() || 'FILE', isGeo: false };
};

export const UploadDropzone: React.FC<UploadDropzoneProps> = ({
  title,
  description,
  dropLabel,
  acceptedFormats,
  formatHint,
  ctaLabel = 'Choose file',
  badge,
  dotColor,
  accept = '.png,.jpg,.jpeg,.tif,.tiff,image/png,image/jpeg,image/tiff',
  file,
  onFileSelect,
  onRemoveFile,
  disabled = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (disabled) return;
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      onFileSelect(files[0]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onFileSelect(files[0]);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col justify-between shadow-xs">
      {(title || badge) && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-2">
              {dotColor && <span className={`w-2 h-2 rounded-full ${dotColor}`} />}
              {title && (
                <span className="text-xs font-semibold text-slate-900 uppercase tracking-wide">
                  {title}
                </span>
              )}
            </div>
            {badge}
          </div>
          {description && (
            <p className="text-xs text-slate-500">
              {description}
            </p>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        disabled={disabled}
        className="sr-only"
      />

      {!file ? (
        <div
          tabIndex={disabled ? -1 : 0}
          role="button"
          aria-label={title ? `Upload ${title}` : dropLabel}
          onKeyDown={(e) => {
            if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => {
            if (!disabled) fileInputRef.current?.click();
          }}
          className={`border-2 border-dashed rounded-xl p-6 sm:p-8 text-center cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 flex flex-col items-center justify-center min-h-[190px] ${
            disabled ? 'opacity-50 cursor-not-allowed' : ''
          } ${
            isDragging
              ? 'border-slate-900 bg-slate-50'
              : 'border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50'
          }`}
        >
          <div className="w-10 h-10 rounded-full bg-white border border-slate-200 text-slate-700 flex items-center justify-center mb-2.5 shadow-2xs">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </div>
          <span className="text-xs font-semibold text-slate-800 font-heading">
            {dropLabel}
          </span>
          <span className="text-[11px] text-slate-400 mt-1 mb-3">
            {formatHint || acceptedFormats || 'Drag and drop your image here, or choose a file'}
          </span>
          {ctaLabel && (
            <button
              type="button"
              tabIndex={-1}
              className="bg-[#0F172A] hover:bg-slate-800 text-white text-xs font-medium px-3.5 py-1.5 rounded-lg shadow-2xs transition-colors pointer-events-none"
            >
              {ctaLabel}
            </button>
          )}
        </div>
      ) : (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 flex flex-col justify-between gap-3 min-h-[190px]">
          <div className="flex items-start space-x-3">
            <div className="w-10 h-10 rounded-lg bg-white border border-slate-200 text-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-2xs">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-slate-900 truncate" title={file.name}>
                {file.name}
              </p>
              <div className="flex items-center space-x-1.5 mt-1">
                {(() => {
                  const badgeInfo = getFileFormatBadge(file.name);
                  return (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                        badgeInfo.isGeo
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-white text-slate-700 border border-slate-200'
                      }`}
                    >
                      {badgeInfo.label}
                    </span>
                  );
                })()}
                <span className="text-[11px] font-mono text-slate-500">
                  Size: {formatFileSize(file.size)}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center space-x-2 pt-2 border-t border-slate-200/80">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="flex-1 text-xs text-slate-700 hover:text-slate-900 font-medium py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
            >
              Change
            </button>
            {onRemoveFile && (
              <button
                type="button"
                onClick={onRemoveFile}
                disabled={disabled}
                className="flex-1 text-xs text-rose-600 hover:text-rose-800 font-medium py-1.5 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 transition-colors focus:outline-none focus:ring-2 focus:ring-rose-500"
              >
                Remove File
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
