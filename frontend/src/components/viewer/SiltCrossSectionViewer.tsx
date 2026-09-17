import { useEffect, useRef } from 'react';
import { SiltCrossSectionScene } from '../../viewer/SiltCrossSectionScene';

interface SiltCrossSectionViewerProps {
  crossSectionProfile: number[];
  predictedSscMgL: number;
  /**
   * Visual ceiling for "fully silted." Deliberately the same GAUGE_MAX used
   * by DredgingIndicator's gauge (real p33/p66 tercile-derived thresholds),
   * not the heatmap's p99-based 900 mg/L ceiling — that ceiling is tuned
   * for compressing a heavy-tailed color ramp, not for a 0-1 fill fraction.
   * At 900, every real (non-flood) reading (1-50 mg/L) rounds to an
   * invisible sliver; against the same scale the dredging indicator itself
   * uses, "moderate"/"high" readings actually read as visibly silted.
   */
  normalizationCeilingMgL?: number;
}

export const SiltCrossSectionViewer: React.FC<SiltCrossSectionViewerProps> = ({
  crossSectionProfile,
  predictedSscMgL,
  normalizationCeilingMgL = 40,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<SiltCrossSectionScene | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const scene = new SiltCrossSectionScene(containerRef.current);
    sceneRef.current = scene;
    return () => {
      scene.dispose();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!sceneRef.current || crossSectionProfile.length === 0) return;
    const intensity = Math.min(1, Math.max(0, predictedSscMgL / normalizationCeilingMgL));
    sceneRef.current.build(crossSectionProfile, intensity);
  }, [crossSectionProfile, predictedSscMgL, normalizationCeilingMgL]);

  return (
    <div className="w-full h-full bg-white border border-slate-200 rounded-xl p-4 sm:p-5 flex flex-col flex-1 shadow-xs">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-slate-900 font-heading">Channel Cross-Section</h3>
        <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
          Orbit & Zoom
        </span>
      </div>
      <div className="flex-1 relative bg-[#F1F5F9] rounded-lg overflow-hidden min-h-[440px] sm:min-h-[560px] border border-slate-200 shadow-inner">
        <div ref={containerRef} className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing" />
      </div>
      <div className="flex items-center justify-center gap-4 pt-2.5 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: '#5e9fd4' }} />
          Water Sheen
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: '#8a6a44' }} />
          Settled Sediment Bed
        </span>
      </div>
      <p className="text-[10px] text-slate-400 text-center pt-1">
        Interactive 3D model with real satellite-derived channel bed profile.
      </p>
    </div>
  );
};
