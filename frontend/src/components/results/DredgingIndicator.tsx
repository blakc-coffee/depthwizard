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

const LEVEL_COLORS: Record<DredgingLevel, { bg: string; text: string; border: string; dot: string }> = {
  low: { bg: 'bg-green-50', text: 'text-green-800', border: 'border-green-200', dot: '#16a34a' },
  moderate: { bg: 'bg-amber-50', text: 'text-amber-800', border: 'border-amber-200', dot: '#d97706' },
  high: { bg: 'bg-red-50', text: 'text-red-800', border: 'border-red-200', dot: '#dc2626' },
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

      {/* Indicator 1: colored badge */}
      <div className={`rounded-lg border px-3 py-2 text-xs ${colors.bg} ${colors.text} ${colors.border}`}>
        <span className="font-semibold uppercase tracking-wide">{level}</span>
        <p className="mt-0.5 text-[11px] leading-relaxed">{label}</p>
      </div>

      {/* Indicator 2: gauge/meter positioned against the real tercile thresholds */}
      <div>
        <div className="relative h-2.5 rounded-full bg-slate-100 overflow-hidden border border-slate-200/50">
          <div className="absolute inset-y-0 left-0 bg-emerald-400" style={{ width: `${lowPct}%` }} />
          <div className="absolute inset-y-0 bg-amber-400" style={{ left: `${lowPct}%`, width: `${highPct - lowPct}%` }} />
          <div className="absolute inset-y-0 bg-rose-400" style={{ left: `${highPct}%`, right: 0 }} />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-1.5 h-4 bg-slate-900 rounded-full shadow-xs"
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
