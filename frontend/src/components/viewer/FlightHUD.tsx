import React from 'react';
import { FlightTelemetry } from '../../viewer/TerrainSceneManager';

interface FlightHUDProps {
  telemetry: FlightTelemetry | null;
}

export const FlightHUD: React.FC<FlightHUDProps> = ({ telemetry }) => {
  if (!telemetry) return null;

  const { altitude, headingDeg, speedMultiplier } = telemetry;

  // Cardinal direction label based on heading angle
  const getCardinal = (deg: number): string => {
    if (deg >= 337.5 || deg < 22.5) return 'N';
    if (deg >= 22.5 && deg < 67.5) return 'NE';
    if (deg >= 67.5 && deg < 112.5) return 'E';
    if (deg >= 112.5 && deg < 157.5) return 'SE';
    if (deg >= 157.5 && deg < 202.5) return 'S';
    if (deg >= 202.5 && deg < 247.5) return 'SW';
    if (deg >= 247.5 && deg < 292.5) return 'W';
    return 'NW';
  };

  const cardinal = getCardinal(headingDeg);
  const isTurbo = speedMultiplier > 1.5;

  return (
    <div
      data-testid="flight-hud"
      className="absolute top-3 left-3 z-10 flex flex-col space-y-1.5 pointer-events-none select-none"
    >
      {/* Primary Flight Telemetry Dark Chip HUD */}
      <div className="bg-[#1e1b2e]/90 backdrop-blur-md border border-[#2b2742]/60 text-white rounded-lg px-2.5 py-1.5 shadow-sm flex items-center space-x-3 pointer-events-auto">
        {/* Rotating Compass Dial */}
        <div
          aria-label={`Compass heading ${headingDeg} degrees ${cardinal}`}
          className="relative w-7 h-7 rounded-full bg-[#25213b]/80 border border-[#363052]/50 flex items-center justify-center flex-shrink-0"
        >
          <div
            className="w-full h-full flex items-center justify-center transition-transform duration-100 ease-out"
            style={{ transform: `rotate(${-headingDeg}deg)` }}
          >
            {/* Compass Needle */}
            <div className="relative w-2 h-5 flex flex-col items-center">
              <div className="w-0 h-0 border-l-[3px] border-l-transparent border-r-[3px] border-r-transparent border-b-[8px] border-b-[#818cf8]" />
              <div className="w-0 h-0 border-l-[3px] border-l-transparent border-r-[3px] border-r-transparent border-t-[8px] border-t-[#4f476e]" />
            </div>
          </div>
          <span className="absolute -top-1 text-[7px] font-mono font-bold text-indigo-400">N</span>
        </div>

        {/* Heading & Altitude Stats */}
        <div className="flex items-center space-x-2.5">
          <div className="flex flex-col">
            <span className="text-[9px] font-mono uppercase tracking-wider text-slate-400">HDG</span>
            <span className="text-xs font-mono font-bold text-white leading-tight">
              {String(headingDeg).padStart(3, '0')}° {cardinal}
            </span>
          </div>
          <div className="flex flex-col">
            <span className="text-[9px] font-mono uppercase tracking-wider text-slate-400">ALT</span>
            <span className="text-xs font-mono font-bold text-indigo-300 leading-tight">{altitude}m</span>
          </div>
        </div>

        {/* Subtle Separator */}
        <div className="h-6 w-px bg-[#2f2a47]" />

        {/* Speed Mode Badge */}
        <div className="flex items-center">
          <span
            className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full ${
              isTurbo
                ? 'bg-indigo-500/25 border border-indigo-400/30 text-indigo-300 font-bold'
                : 'bg-[#28233d] border border-[#3b3456]/60 text-slate-200'
            }`}
          >
            {isTurbo ? '⚡ Turbo' : '1x Cruise'}
          </span>
        </div>
      </div>

      {/* Flight Key Hints Banner - Dark Chip */}
      <div className="bg-[#1e1b2e]/90 backdrop-blur-md border border-[#2b2742]/60 rounded-md px-2.5 py-1 text-[10px] text-slate-300 flex items-center space-x-1.5 pointer-events-auto">
        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
        <span>
          <kbd className="font-mono bg-[#28233d] border border-[#3b3456]/60 text-slate-200 px-1 py-0.5 rounded text-[9px]">WASD</kbd> fly ·{' '}
          <kbd className="font-mono bg-[#28233d] border border-[#3b3456]/60 text-slate-200 px-1 py-0.5 rounded text-[9px]">Q</kbd>/<kbd className="font-mono bg-[#28233d] border border-[#3b3456]/60 text-slate-200 px-1 py-0.5 rounded text-[9px]">E</kbd> alt ·{' '}
          <kbd className="font-mono bg-[#28233d] border border-[#3b3456]/60 text-slate-200 px-1 py-0.5 rounded text-[9px]">Shift</kbd> turbo
        </span>
      </div>
    </div>
  );
};
