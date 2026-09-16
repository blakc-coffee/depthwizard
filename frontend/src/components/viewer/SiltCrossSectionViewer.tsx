import { useEffect, useRef } from 'react';
import { SiltCrossSectionScene } from '../../viewer/SiltCrossSectionScene';

interface SiltCrossSectionViewerProps {
  crossSectionProfile: number[];
  predictedSscMgL: number;
  /** Same ceiling ml/river_silt_pipeline.py uses to normalize the heatmap — keeps the two views visually consistent. */
  normalizationCeilingMgL?: number;
}

export const SiltCrossSectionViewer: React.FC<SiltCrossSectionViewerProps> = ({
  crossSectionProfile,
  predictedSscMgL,
  normalizationCeilingMgL = 900,
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
    <div className="w-full h-full bg-[#f6f8fa] border border-[#cdd2d9] rounded-[12px] p-4 sm:p-5 flex flex-col flex-1">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-[#36394a] font-heading">Cross-Section</h3>
        <span className="text-[11px] text-[#818898]">Drag to tilt · Scroll to zoom</span>
      </div>
      <div className="flex-1 relative bg-[#e2e6eb] rounded-[12px] overflow-hidden min-h-[280px] border border-[#cdd2d9]/80 shadow-inner">
        <div ref={containerRef} className="w-full h-full absolute inset-0 cursor-grab active:cursor-grabbing" />
      </div>
      <div className="flex items-center justify-center gap-4 pt-2.5 text-[11px] text-[#818898]">
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: '#5e9fd4' }} />
          Water
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: '#8a6a44' }} />
          Sediment
        </span>
      </div>
      <p className="text-[10px] text-[#a3a9b5] text-center pt-1">
        Stylized cross-section — real image-derived channel shape, not a literal bathymetric survey.
      </p>
    </div>
  );
};
