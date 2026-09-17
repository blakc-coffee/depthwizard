import { useEffect, useRef, useState } from 'react';
import { OutputType } from '../../lib/types';
import { DisasterMode, FlightTelemetry, TerrainSceneManager, ViewMode } from '../../viewer/TerrainSceneManager';
import { FlightHUD } from './FlightHUD';

interface TerrainViewerProps {
  heightmapUrl: string;
  textureUrl: string;
  confidenceMapUrl?: string | null;
  outputType: OutputType;
  maxHeight: number;
  disasterMode?: DisasterMode;
}

export const TerrainViewer: React.FC<TerrainViewerProps> = ({
  heightmapUrl,
  textureUrl,
  confidenceMapUrl,
  outputType,
  maxHeight,
  disasterMode = 'before',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const managerRef = useRef<TerrainSceneManager | null>(null);

  const [activeMode, setActiveMode] = useState<ViewMode>('3d');
  const [loading, setLoading] = useState<boolean>(true);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [exaggeration, setExaggeration] = useState<number>(2.2);
  const [telemetry, setTelemetry] = useState<FlightTelemetry | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    let isSubscribed = true;
    setLoading(true);
    setViewerError(null);

    let manager: TerrainSceneManager | null = null;

    try {
      manager = new TerrainSceneManager(containerRef.current);
      managerRef.current = manager;

      manager.setTelemetryCallback((data) => {
        if (isSubscribed) {
          setTelemetry(data);
        }
      });

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

  useEffect(() => {
    if (disasterMode && managerRef.current) {
      managerRef.current.setDisasterMode(disasterMode);
    }
  }, [disasterMode]);

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
    <div className="relative w-full h-full min-h-[550px] sm:min-h-[640px] rounded-xl overflow-hidden bg-[#F1F5F9] border border-slate-200/80 shadow-xs flex flex-col">
      {/* Tactical Flight Telemetry HUD (top-left) */}
      <FlightHUD telemetry={telemetry} />

      {/* Floating Center View Mode Pill Switcher (Normal / Slope) - Continuous Segmented Pill */}
      <div className="absolute top-3.5 left-1/2 -translate-x-1/2 z-10 flex items-center bg-slate-900/75 backdrop-blur-md rounded-full p-0.5 shadow-sm">
        <button
          type="button"
          onClick={() => handleModeChange('3d')}
          className={`px-3.5 py-1 text-xs font-medium rounded-full transition-all focus:outline-none ${
            activeMode === '3d'
              ? 'bg-[#5e4cff] text-white shadow-xs font-semibold'
              : 'text-slate-300 hover:text-white'
          }`}
        >
          Normal
        </button>
        <button
          type="button"
          onClick={() => handleModeChange('2d_heightmap')}
          className={`px-3.5 py-1 text-xs font-medium rounded-full transition-all focus:outline-none ${
            activeMode === '2d_heightmap'
              ? 'bg-[#5e4cff] text-white shadow-xs font-semibold'
              : 'text-slate-300 hover:text-white'
          }`}
        >
          Slope
        </button>
      </div>

      {/* Floating Top-Right Controls: Relief & Reset - Dark Chip */}
      <div className="absolute top-3.5 right-3.5 z-10 flex items-center space-x-2 bg-slate-900/75 backdrop-blur-md text-white rounded-full px-3 py-1 shadow-sm text-xs">
        <span className="text-slate-400 font-medium select-none text-[11px]">Relief:</span>
        <input
          type="range"
          min="0.8"
          max="4.5"
          step="0.1"
          value={exaggeration}
          onChange={handleExaggerationChange}
          className="w-16 sm:w-20 h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-[#5e4cff]"
          title={`Vertical Exaggeration: ${exaggeration.toFixed(1)}x`}
        />
        <span className="font-mono text-[11px] font-semibold text-slate-200 min-w-[28px] text-right">
          {exaggeration.toFixed(1)}x
        </span>
        <div className="h-3 w-px bg-slate-700 mx-0.5" />
        <button
          type="button"
          onClick={handleResetView}
          className="text-slate-300 hover:text-white font-medium text-[11px] transition-colors focus:outline-none"
        >
          Reset
        </button>
      </div>

      {/* Difference Map Legend Overlay - Dark Chip */}
      {disasterMode === 'difference' && (
        <div className="absolute top-12 right-3.5 z-10 bg-slate-900/75 backdrop-blur-md px-3 py-1.5 rounded-lg shadow-sm text-[11px] text-white flex items-center space-x-3 pointer-events-none select-none animate-in fade-in duration-150">
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500 shadow-2xs" />
            <span className="font-semibold text-rose-300">Collapse</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-2xs" />
            <span className="font-semibold text-cyan-300">Flooded</span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-slate-400 shadow-2xs" />
            <span className="font-medium text-slate-400">Stable</span>
          </div>
        </div>
      )}

      {/* After Disaster State Overlay Badge - Dark Chip */}
      {disasterMode === 'after' && (
        <div className="absolute top-12 right-3.5 z-10 bg-slate-900/75 backdrop-blur-md px-3 py-1 rounded-full shadow-sm text-[11px] text-slate-200 pointer-events-none select-none animate-in fade-in duration-150">
          <span className="font-medium">Post-Disaster View</span>
        </div>
      )}

      {/* Loading State Overlay */}
      {loading && (
        <div className="absolute inset-0 z-20 bg-[#F1F5F9]/90 flex items-center justify-center space-x-3 text-sm text-slate-700 font-medium">
          <svg
            className="animate-spin h-5 w-5 text-slate-900"
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

      {/* Error State Overlay */}
      {viewerError && (
        <div className="absolute inset-0 z-20 bg-white/95 p-6 flex flex-col items-center justify-center text-center space-y-3 text-slate-800">
          <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center">
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
          <p className="text-xs text-slate-400 max-w-md">{viewerError}</p>
        </div>
      )}

      {/* Full-bleed 3D WebGL Canvas */}
      <div ref={containerRef} className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing" />

      {/* Floating Bottom Navigation Hint - Dark Chip */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 bg-slate-900/60 backdrop-blur-md px-3.5 py-1 rounded-full text-[10px] text-slate-300 pointer-events-none select-none shadow-sm whitespace-nowrap">
        WASD/Arrows to fly · Q/E altitude · Drag to orbit · Scroll to zoom
      </div>
    </div>
  );
};
