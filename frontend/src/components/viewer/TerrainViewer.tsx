import { useEffect, useRef, useState } from 'react';
import { OutputType } from '../../lib/types';
import { TerrainSceneManager, ViewMode } from '../../viewer/TerrainSceneManager';

interface TerrainViewerProps {
  heightmapUrl: string;
  textureUrl: string;
  confidenceMapUrl?: string | null;
  outputType: OutputType;
  maxHeight: number;
}

export const TerrainViewer: React.FC<TerrainViewerProps> = ({
  heightmapUrl,
  textureUrl,
  confidenceMapUrl,
  outputType,
  maxHeight,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const managerRef = useRef<TerrainSceneManager | null>(null);

  const [activeMode, setActiveMode] = useState<ViewMode>('3d');
  const [loading, setLoading] = useState<boolean>(true);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [exaggeration, setExaggeration] = useState<number>(2.2);

  useEffect(() => {
    if (!containerRef.current) return;

    let isSubscribed = true;
    setLoading(true);
    setViewerError(null);

    let manager: TerrainSceneManager | null = null;

    try {
      manager = new TerrainSceneManager(containerRef.current);
      managerRef.current = manager;

      manager
        .loadTerrain(
          {
            heightmapUrl,
            textureUrl,
            maxHeight,
            isAbsolute: outputType === 'absolute_dsm',
            verticalExaggeration: exaggeration,
          },
          confidenceMapUrl
        )
        .then(() => {
          if (isSubscribed) {
            setLoading(false);
          }
        })
        .catch((err) => {
          if (isSubscribed) {
            console.error('Terrain mesh building error:', err);
            setViewerError('Could not decode heightmap or render WebGL 3D terrain mesh.');
            setLoading(false);
          }
        });
    } catch (err) {
      if (isSubscribed) {
        console.error('WebGL initialization error:', err);
        setViewerError('WebGL renderer initialization failed. Please check browser hardware acceleration.');
        setLoading(false);
      }
    }

    return () => {
      isSubscribed = false;
      if (manager) {
        manager.dispose();
        managerRef.current = null;
      }
    };
  }, [heightmapUrl, textureUrl, confidenceMapUrl, maxHeight, outputType]);

  const handleModeChange = (mode: ViewMode) => {
    setActiveMode(mode);
    managerRef.current?.setViewMode(mode);
  };

  const handleResetView = () => {
    managerRef.current?.resetView();
  };

  const handleExaggerationChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    setExaggeration(val);
    managerRef.current?.setHeightExaggeration(val);
  };

  return (
    <div className="w-full h-full bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-4 sm:p-5 flex flex-col flex-1 max-w-full overflow-hidden">
      {/* Viewer Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-base font-semibold text-[#36394a] font-heading">
            3D Viewer
          </h3>

          {/* Vertical Relief Exaggeration Slider */}
          <div className="flex items-center space-x-2 bg-white px-3 py-1.5 rounded-[8px] border border-[#cdd2d9] shadow-2xs">
            <span className="text-xs text-[#666d80] font-medium select-none">Relief:</span>
            <input
              type="range"
              min="0.8"
              max="4.5"
              step="0.1"
              value={exaggeration}
              onChange={handleExaggerationChange}
              className="w-20 sm:w-28 h-1.5 bg-[#e2e4e9] rounded-lg appearance-none cursor-pointer accent-[#5e4cff]"
              title={`Vertical Exaggeration: ${exaggeration.toFixed(1)}x`}
            />
            <span className="text-xs font-mono font-semibold text-[#5e4cff] min-w-[32px] text-right">
              {exaggeration.toFixed(1)}x
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleResetView}
            aria-label="Reset View"
            className="text-xs text-[#36394a] hover:bg-[#f6f8fa] font-medium px-3.5 py-1.5 rounded-[8px] border border-[#cdd2d9] bg-white transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] shadow-2xs"
          >
            Reset View
          </button>
        </div>
      </div>

      {/* 3D WebGL Canvas Container: Clean soft gray exhibition studio */}
      <div className="flex-1 w-full relative bg-[#e2e6eb] rounded-[12px] overflow-hidden min-h-[360px] sm:min-h-[440px] border border-[#cdd2d9]/80 shadow-inner">
        {/* Interactive Flight Controls Badge */}
        <div className="absolute top-3 left-3 z-10 hidden sm:flex items-center space-x-1.5 bg-white/90 backdrop-blur-xs px-2.5 py-1 rounded-[6px] border border-[#cdd2d9] shadow-2xs text-[11px] font-medium text-[#36394a] select-none pointer-events-none">
          <span className="w-1.5 h-1.5 rounded-full bg-[#5e4cff]" />
          <span>Fly: <kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded text-[10px] border border-[#cdd2d9]">WASD</kbd> · Altitude: <kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded text-[10px] border border-[#cdd2d9]">Q</kbd>/<kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded text-[10px] border border-[#cdd2d9]">E</kbd></span>
        </div>

        {loading && (
          <div className="absolute inset-0 z-20 bg-[#e2e6eb]/90 flex items-center justify-center space-x-3 text-sm text-[#36394a] font-medium">
            <svg
              className="animate-spin h-5 w-5 text-[#5e4cff]"
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
            <span>Building solid 3D terrain block…</span>
          </div>
        )}

        {viewerError && (
          <div className="absolute inset-0 z-20 bg-white/95 p-6 flex flex-col items-center justify-center text-center space-y-3 text-[#36394a]">
            <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h4 className="text-sm font-semibold font-heading">3D Terrain Rendering Unavailable</h4>
            <p className="text-xs text-[#818898] max-w-md">{viewerError}</p>
          </div>
        )}

        <div ref={containerRef} className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing" />
      </div>

      {/* Caption under canvas */}
      <p className="text-[11px] text-[#818898] text-center my-2.5">
        WASD or Arrows to fly · Q/E for altitude · Drag to orbit · Scroll to zoom · Relief adjusts heights
      </p>

      {/* Bottom Segmented Overlay Pills matching image_3.png */}
      <div className="flex flex-wrap items-center justify-center gap-1.5 pt-1 border-t border-[#cdd2d9]/60 max-w-full overflow-hidden">
        <span className="text-xs text-[#818898] font-medium mr-1.5">Overlay</span>

        <button
          type="button"
          onClick={() => handleModeChange('3d')}
          className={`px-3.5 sm:px-5 py-1 text-xs font-medium rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
            activeMode === '3d'
              ? 'bg-[#5e4cff] text-white shadow-xs'
              : 'bg-white border border-[#cdd2d9] text-[#36394a] hover:bg-[#f6f8fa]'
          }`}
        >
          Normal
        </button>

        <button
          type="button"
          onClick={() => handleModeChange('2d_heightmap')}
          className={`px-3.5 sm:px-5 py-1 text-xs font-medium rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
            activeMode === '2d_heightmap'
              ? 'bg-[#5e4cff] text-white shadow-xs'
              : 'bg-white border border-[#cdd2d9] text-[#36394a] hover:bg-[#f6f8fa]'
          }`}
        >
          Slope
        </button>

        <button
          type="button"
          disabled={!confidenceMapUrl}
          onClick={() => confidenceMapUrl && handleModeChange('confidence')}
          title={!confidenceMapUrl ? 'Confidence Map unavailable for this job' : 'View Confidence Map'}
          className={`px-3.5 sm:px-5 py-1 text-xs font-medium rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff] ${
            !confidenceMapUrl
              ? 'opacity-40 cursor-not-allowed bg-white border border-[#cdd2d9] text-[#818898]'
              : activeMode === 'confidence'
              ? 'bg-[#5e4cff] text-white shadow-xs'
              : 'bg-white border border-[#cdd2d9] text-[#36394a] hover:bg-[#f6f8fa]'
          }`}
        >
          Confidence
        </button>

        <button
          type="button"
          className="px-3.5 sm:px-5 py-1 text-xs font-medium rounded-full bg-white border border-[#cdd2d9] text-[#36394a] hover:bg-[#f6f8fa] transition-colors focus:outline-none focus:ring-2 focus:ring-[#5e4cff]"
        >
          Validation
        </button>
      </div>
    </div>
  );
};
