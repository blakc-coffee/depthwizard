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
        .loadTerrain({
          heightmapUrl,
          textureUrl,
          maxHeight,
          isAbsolute: outputType === 'absolute_dsm',
        })
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
  }, [heightmapUrl, textureUrl, maxHeight, outputType]);

  const handleModeChange = (mode: ViewMode) => {
    setActiveMode(mode);
    managerRef.current?.setViewMode(mode);
  };

  const handleResetView = () => {
    managerRef.current?.resetView();
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#FDFCF8] border border-gray-200 rounded-xl overflow-hidden shadow-sm relative min-h-[420px] sm:min-h-[500px]">
      {/* Accessible Control Bar */}
      <div className="bg-[#FDFCF8] border-b border-gray-200 px-4 py-3 flex flex-wrap items-center justify-between gap-3 z-10">
        <div className="flex items-center space-x-1.5 bg-[#ECE9DD]/60 p-1 rounded-lg">
          <button
            type="button"
            onClick={() => handleModeChange('3d')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600 ${
              activeMode === '3d'
                ? 'bg-purple-700 text-white shadow-xs'
                : 'text-gray-700 hover:text-gray-900 hover:bg-[#ECE9DD]'
            }`}
          >
            3D Terrain
          </button>
          <button
            type="button"
            onClick={() => handleModeChange('2d_heightmap')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600 ${
              activeMode === '2d_heightmap'
                ? 'bg-purple-700 text-white shadow-xs'
                : 'text-gray-700 hover:text-gray-900 hover:bg-[#ECE9DD]'
            }`}
          >
            2D Heightmap
          </button>
          <button
            type="button"
            disabled={!confidenceMapUrl}
            onClick={() => confidenceMapUrl && handleModeChange('confidence')}
            title={!confidenceMapUrl ? 'Confidence Map unavailable for this job' : 'View Confidence Map'}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600 ${
              !confidenceMapUrl
                ? 'opacity-40 cursor-not-allowed text-gray-500'
                : activeMode === 'confidence'
                ? 'bg-purple-700 text-white shadow-xs'
                : 'text-gray-700 hover:text-gray-900 hover:bg-[#ECE9DD]'
            }`}
          >
            Confidence Map
          </button>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleResetView}
            aria-label="Reset 3D camera view"
            className="text-xs text-gray-700 hover:text-purple-900 font-medium px-3 py-1.5 rounded-md border border-gray-300 hover:bg-[#ECE9DD] transition-colors focus:outline-none focus:ring-2 focus:ring-purple-600"
          >
            Reset View
          </button>
        </div>
      </div>

      {/* 3D WebGL Canvas Container */}
      <div className="flex-1 w-full h-full relative bg-[#F6F4EC] min-h-[360px]">
        {loading && (
          <div className="absolute inset-0 z-20 bg-[#FDFCF8]/90 flex items-center justify-center space-x-3 text-sm text-gray-700 font-medium">
            <svg
              className="animate-spin h-5 w-5 text-purple-700"
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
            <span>Building 3D terrain mesh…</span>
          </div>
        )}

        {viewerError && (
          <div className="absolute inset-0 z-20 bg-[#FDFCF8] p-6 flex flex-col items-center justify-center text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h4 className="text-sm font-semibold text-gray-900">3D Terrain Rendering Unavailable</h4>
            <p className="text-xs text-gray-600 max-w-md">{viewerError}</p>
          </div>
        )}

        <div ref={containerRef} className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing" />
      </div>
    </div>
  );
};
