import { useEffect, useRef, useState } from 'react';

export type SiltOutputType = 'absolute_ssc' | 'relative_silt_index';

export interface SiltRegionBreakdown {
  label: string;
  value_mg_l: number;
}

interface SiltHeatmapViewerProps {
  /** Source RGB crop (the river reach image the user uploaded/pulled). */
  sourceImageUrl: string;
  /**
   * Grayscale PNG, one pixel per source pixel, 0-255 encoding normalized
   * silt intensity (low -> high). Same "PNG carries the payload" contract
   * as TerrainViewer's heightmapUrl — no separate data format to parse.
   */
  heatmapUrl: string;
  outputType: SiltOutputType;
  meanSscMgL?: number | null;
  peakSscMgL?: number | null;
  /** 0-1, mirrors the confidence dots already used elsewhere in this app. */
  confidence?: number | null;
  confidenceNote?: string | null;
  regionBreakdown?: SiltRegionBreakdown[];
}

// Blue (low) -> brown (mid) -> red (high), placeholder per docs/phase_river_silt.md
// §4 — not yet validated for color-blind accessibility (flagged there too).
const COLOR_STOPS: [number, number, number][] = [
  [30, 90, 200],   // low
  [150, 110, 60],  // mid
  [200, 40, 30],   // high
];

function lerpColor(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t));
  const segment = clamped < 0.5 ? 0 : 1;
  const localT = clamped < 0.5 ? clamped / 0.5 : (clamped - 0.5) / 0.5;
  const [r0, g0, b0] = COLOR_STOPS[segment];
  const [r1, g1, b1] = COLOR_STOPS[segment + 1];
  return [r0 + (r1 - r0) * localT, g0 + (g1 - g0) * localT, b0 + (b1 - b0) * localT];
}

export const SiltHeatmapViewer: React.FC<SiltHeatmapViewerProps> = ({
  sourceImageUrl,
  heatmapUrl,
  outputType,
  meanSscMgL,
  peakSscMgL,
  confidence,
  confidenceNote,
  regionBreakdown,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const heatmapDataRef = useRef<ImageData | null>(null);
  // Lower than a first instinct of ~0.75: this tint spans the whole photo,
  // not just the water (no reliable RGB-only water mask — see
  // DENSE_HEATMAP_CAVEAT), so a heavy default would bury the source image
  // under one flat color wash instead of reading as a legible blend.
  const [opacity, setOpacity] = useState<number>(0.4);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hoverValue, setHoverValue] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setError('Canvas 2D context unavailable in this browser.');
      setLoading(false);
      return;
    }

    const sourceImg = new Image();
    const heatmapImg = new Image();
    let loadedCount = 0;

    const onBothLoaded = () => {
      if (cancelled) return;
      canvas.width = sourceImg.naturalWidth;
      canvas.height = sourceImg.naturalHeight;

      // Read the heatmap's raw grayscale values off-screen once, so hover
      // lookups and opacity redraws don't re-decode the PNG every frame.
      const offscreen = document.createElement('canvas');
      offscreen.width = heatmapImg.naturalWidth;
      offscreen.height = heatmapImg.naturalHeight;
      const offCtx = offscreen.getContext('2d');
      if (!offCtx) {
        setError('Could not read heatmap pixel data.');
        setLoading(false);
        return;
      }
      offCtx.drawImage(heatmapImg, 0, 0);
      heatmapDataRef.current = offCtx.getImageData(0, 0, offscreen.width, offscreen.height);

      setLoading(false);
    };

    const onLoad = () => {
      loadedCount += 1;
      if (loadedCount === 2) onBothLoaded();
    };
    const onError = () => {
      if (!cancelled) {
        setError('Could not load source image or silt heatmap.');
        setLoading(false);
      }
    };

    sourceImg.onload = onLoad;
    sourceImg.onerror = onError;
    heatmapImg.onload = onLoad;
    heatmapImg.onerror = onError;
    sourceImg.src = sourceImageUrl;
    heatmapImg.src = heatmapUrl;

    return () => {
      cancelled = true;
    };
  }, [sourceImageUrl, heatmapUrl]);

  // Redraw whenever opacity changes or the images finish loading — cheap
  // (one drawImage + one colorized overlay pass), no need for a full effect
  // re-run tied to the network loads above.
  useEffect(() => {
    if (loading || error) return;
    const canvas = canvasRef.current;
    const heatmapData = heatmapDataRef.current;
    if (!canvas || !heatmapData) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const sourceImg = new Image();
    sourceImg.src = sourceImageUrl;
    sourceImg.onload = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(sourceImg, 0, 0, canvas.width, canvas.height);

      const overlay = ctx.createImageData(canvas.width, canvas.height);
      const scaleX = heatmapData.width / canvas.width;
      const scaleY = heatmapData.height / canvas.height;
      for (let y = 0; y < canvas.height; y++) {
        for (let x = 0; x < canvas.width; x++) {
          const srcIdx = (Math.floor(y * scaleY) * heatmapData.width + Math.floor(x * scaleX)) * 4;
          const intensity = heatmapData.data[srcIdx] / 255;
          const [r, g, b] = lerpColor(intensity);
          const dstIdx = (y * canvas.width + x) * 4;
          overlay.data[dstIdx] = r;
          overlay.data[dstIdx + 1] = g;
          overlay.data[dstIdx + 2] = b;
          overlay.data[dstIdx + 3] = Math.round(opacity * 255);
        }
      }
      const overlayCanvas = document.createElement('canvas');
      overlayCanvas.width = canvas.width;
      overlayCanvas.height = canvas.height;
      overlayCanvas.getContext('2d')?.putImageData(overlay, 0, 0);
      ctx.drawImage(overlayCanvas, 0, 0);
    };
  }, [opacity, loading, error, sourceImageUrl]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const heatmapData = heatmapDataRef.current;
    if (!canvas || !heatmapData) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor(((e.clientX - rect.left) / rect.width) * heatmapData.width);
    const y = Math.floor(((e.clientY - rect.top) / rect.height) * heatmapData.height);
    if (x < 0 || y < 0 || x >= heatmapData.width || y >= heatmapData.height) return;
    const idx = (y * heatmapData.width + x) * 4;
    const intensity = heatmapData.data[idx] / 255;
    // Absolute mode: scale intensity by the scene's own peak so hover reads
    // a plausible mg/L; relative mode has no real unit, show 0-100 instead.
    setHoverValue(outputType === 'absolute_ssc' && peakSscMgL ? intensity * peakSscMgL : intensity * 100);
  };

  const isAbsolute = outputType === 'absolute_ssc';
  const unitLabel = isAbsolute ? 'mg/L' : 'relative index';
  const confidenceDots = confidence != null ? Math.round(confidence * 5) : null;

  return (
    <div className="w-full h-full bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-4 sm:p-5 flex flex-col lg:flex-row gap-5 flex-1 max-w-full overflow-hidden">
      {/* Canvas panel */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h3 className="text-base font-semibold text-[#36394a] font-heading">Silt Heatmap</h3>
          <div className="flex items-center space-x-2 bg-white px-3 py-1.5 rounded-[8px] border border-[#cdd2d9] shadow-2xs">
            <span className="text-xs text-[#666d80] font-medium select-none">Opacity:</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={opacity}
              onChange={(e) => setOpacity(parseFloat(e.target.value))}
              className="w-20 sm:w-28 h-1.5 bg-[#e2e4e9] rounded-lg appearance-none cursor-pointer accent-[#5e4cff]"
              aria-label="Heatmap overlay opacity"
            />
            <span className="text-xs font-mono font-semibold text-[#5e4cff] min-w-[36px] text-right">
              {Math.round(opacity * 100)}%
            </span>
          </div>
        </div>

        <div className="flex-1 relative bg-[#e2e6eb] rounded-[12px] overflow-hidden min-h-[300px] sm:min-h-[360px] border border-[#cdd2d9]/80 shadow-inner">
          {loading && (
            <div className="absolute inset-0 z-20 bg-[#e2e6eb]/90 flex items-center justify-center space-x-3 text-sm text-[#36394a] font-medium">
              <svg className="animate-spin h-5 w-5 text-[#5e4cff]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>Loading silt heatmap…</span>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 z-20 bg-white/95 p-6 flex flex-col items-center justify-center text-center space-y-2 text-[#36394a]">
              <h4 className="text-sm font-semibold font-heading">Heatmap Unavailable</h4>
              <p className="text-xs text-[#818898] max-w-md">{error}</p>
            </div>
          )}

          <canvas
            ref={canvasRef}
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setHoverValue(null)}
            className="w-full h-full object-contain cursor-crosshair"
          />

          {hoverValue != null && (
            <div className="absolute top-3 left-3 z-10 bg-white/95 backdrop-blur-xs px-3 py-1.5 rounded-[8px] border border-[#cdd2d9] shadow-2xs text-[11px] font-mono text-[#36394a] pointer-events-none select-none">
              {hoverValue.toFixed(1)} {unitLabel}
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-2 pt-3 text-[11px] text-[#818898]">
          <span>Low</span>
          <div
            className="w-32 h-2.5 rounded-full"
            style={{ background: 'linear-gradient(to right, rgb(30,90,200), rgb(150,110,60), rgb(200,40,30))' }}
            aria-hidden="true"
          />
          <span>High</span>
        </div>
      </div>

      {/* Summary panel */}
      <div className="w-full lg:w-64 flex-shrink-0 flex flex-col gap-3">
        <div className="bg-white rounded-[8px] border border-[#cdd2d9] p-3.5 shadow-2xs">
          <h4 className="text-xs font-semibold text-[#36394a] font-heading mb-2">Silt Summary</h4>
          <dl className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <dt className="text-[#666d80]">Mean SSC</dt>
              <dd className="font-mono font-medium text-[#36394a]">
                {meanSscMgL != null ? `${meanSscMgL.toFixed(0)} mg/L` : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[#666d80]">Peak SSC</dt>
              <dd className="font-mono font-medium text-[#36394a]">
                {peakSscMgL != null ? `${peakSscMgL.toFixed(0)} mg/L` : '—'}
              </dd>
            </div>
            {confidenceDots != null && (
              <div className="flex justify-between items-center">
                <dt className="text-[#666d80]">Confidence</dt>
                <dd className="font-mono text-[#5e4cff]">
                  {'●'.repeat(confidenceDots)}
                  {'○'.repeat(5 - confidenceDots)}
                </dd>
              </div>
            )}
          </dl>
        </div>

        <div
          className={`rounded-[8px] border p-3 text-[11px] ${
            isAbsolute
              ? 'bg-[#dfdbff] text-[#5e4cff] border-[#c8ccf3]'
              : 'bg-amber-50 text-amber-800 border-amber-200'
          }`}
        >
          <span className="font-semibold">{isAbsolute ? 'Absolute SSC (mg/L)' : 'Relative Silt Index'}</span>
          {!isAbsolute && (
            <p className="mt-1">
              No trustworthy gauge anchor{confidenceNote ? ` — ${confidenceNote}` : ''}. Shown as relative plume
              intensity, not absolute mg/L.
            </p>
          )}
        </div>

        {regionBreakdown && regionBreakdown.length > 0 && (
          <div className="bg-white rounded-[8px] border border-[#cdd2d9] p-3.5 shadow-2xs">
            <h4 className="text-xs font-semibold text-[#36394a] font-heading mb-2">Per-Region Breakdown</h4>
            <dl className="space-y-1.5 text-xs">
              {regionBreakdown.map((region) => (
                <div key={region.label} className="flex justify-between">
                  <dt className="text-[#666d80] capitalize">{region.label}</dt>
                  <dd className="font-mono font-medium text-[#36394a]">{region.value_mg_l.toFixed(0)} mg/L</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
};
