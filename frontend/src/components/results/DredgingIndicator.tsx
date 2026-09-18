import { DredgingLevel } from '../../lib/types';

interface DredgingIndicatorProps {
  level: DredgingLevel;
  label: string;
  predictedSscMgL: number;
}

// Real, measured thresholds (ml/river_silt_pipeline.py, tercile split of
// this project's own training data, not an engineering/regulatory
// standard) — mirrored here only for the gauge's visual scale, not
// re-derived independently.
const LOW_THRESHOLD = 7.2;
const HIGH_THRESHOLD = 20.0;
const GAUGE_MAX = 40; // visual ceiling for the gauge track — values above just peg to 100%

const LEVEL_COLORS: Record<DredgingLevel, { text: string; dot: string }> = {
  low: { text: 'text-[#2D5A4C]', dot: '#7FB8A3' },
  moderate: { text: 'text-[#7A5B10]', dot: '#E8C468' },
  high: { text: 'text-[#782830]', dot: '#E08A93' },
};

const LEVEL_ORDER: DredgingLevel[] = ['low', 'moderate', 'high'];

export const DredgingIndicator: React.FC<DredgingIndicatorProps> = ({ level, label, predictedSscMgL }) => {
  const colors = LEVEL_COLORS[level];
  const gaugePct = Math.min(100, (predictedSscMgL / GAUGE_MAX) * 100);
  const lowPct = (LOW_THRESHOLD / GAUGE_MAX) * 100;
  const highPct = (HIGH_THRESHOLD / GAUGE_MAX) * 100;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs space-y-3.5">
      <h4 className="text-xs font-semibold text-slate-900 font-heading">Dredging Recommendation</h4>

      {/* Indicator 1: colored text without border or container box */}
      <div className={`text-xs ${colors.text}`}>
        <span className="font-semibold uppercase tracking-wide">{level}</span>
        <p className="mt-0.5 text-[11px] leading-relaxed">{label}</p>
      </div>

      {/* Indicator 2: gauge/meter with softened muted palette */}
      <div>
        <div className="relative h-2.5 rounded-full bg-slate-100 overflow-hidden border border-slate-200/50">
          <div className="absolute inset-y-0 left-0 bg-[#7FB8A3]" style={{ width: `${lowPct}%` }} />
          <div className="absolute inset-y-0 bg-[#E8C468]" style={{ left: `${lowPct}%`, width: `${highPct - lowPct}%` }} />
          <div className="absolute inset-y-0 bg-[#E08A93]" style={{ left: `${highPct}%`, right: 0 }} />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-1 h-3.5 bg-slate-800 rounded-full"
            style={{ left: `calc(${gaugePct}% - 2px)` }}
            title={`${predictedSscMgL.toFixed(1)} mg/L`}
          />
        </div>
        <div className="flex justify-between text-[10px] text-slate-400 mt-1.5">
          <span>0</span>
          <span>{LOW_THRESHOLD} mg/L</span>
          <span>{HIGH_THRESHOLD} mg/L</span>
          <span>{GAUGE_MAX}+</span>
        </div>
      </div>

      {/* Indicator 3: traffic-light dots */}
      <div className="flex items-center justify-center gap-3">
        {LEVEL_ORDER.map((l) => (
          <span
            key={l}
            className="w-3.5 h-3.5 rounded-full border border-black/10"
            style={{
              background: LEVEL_COLORS[l].dot,
              opacity: l === level ? 1 : 0.2,
              boxShadow: l === level ? `0 0 0 3px ${LEVEL_COLORS[l].dot}33` : 'none',
            }}
            aria-label={l}
          />
        ))}
      </div>
    </div>
  );
};
