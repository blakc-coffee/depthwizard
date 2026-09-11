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
      className="absolute top-3 left-3 z-10 flex flex-col space-y-2 pointer-events-none select-none"
    >
      {/* Primary Flight Telemetry Card */}
      <div className="bg-white/95 backdrop-blur-xs border border-[#cdd2d9] rounded-[10px] p-2.5 shadow-2xs flex items-center space-x-3 pointer-events-auto">
        {/* Rotating Compass Dial */}
        <div
          aria-label={`Compass heading ${headingDeg} degrees ${cardinal}`}
          className="relative w-9 h-9 rounded-full border border-[#cdd2d9] bg-[#f6f8fa] flex items-center justify-center flex-shrink-0"
        >
          <div
            className="w-full h-full flex items-center justify-center transition-transform duration-100 ease-out"
            style={{ transform: `rotate(${-headingDeg}deg)` }}
          >
            {/* Compass Needle (North = purple, South = slate) */}
            <div className="relative w-2.5 h-6 flex flex-col items-center">
              <div className="w-0 h-0 border-l-[3.5px] border-l-transparent border-r-[3.5px] border-r-transparent border-b-[9px] border-b-[#5e4cff]" />
              <div className="w-0 h-0 border-l-[3.5px] border-l-transparent border-r-[3.5px] border-r-transparent border-t-[9px] border-t-[#94a3b8]" />
            </div>
          </div>
          <span className="absolute -top-1 text-[8px] font-mono font-bold text-[#5e4cff]">N</span>
        </div>

        {/* Heading & Altitude Stats */}
        <div className="flex flex-col">
          <div className="flex items-center space-x-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#818898]">HDG</span>
            <span className="text-xs font-mono font-bold text-[#36394a]">
              {String(headingDeg).padStart(3, '0')}° {cardinal}
            </span>
          </div>
          <div className="flex items-center space-x-1.5">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#818898]">ALT</span>
            <span className="text-xs font-mono font-bold text-[#5e4cff]">{altitude}m</span>
          </div>
        </div>

        {/* Vertical Separator */}
        <div className="h-7 w-px bg-[#cdd2d9]" />

        {/* Speed Mode Badge */}
        <div className="flex flex-col items-start">
          <span
            className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full border flex items-center space-x-1 ${
              isTurbo
                ? 'bg-[#dfdbff] text-[#5e4cff] border-[#c8ccf3]'
                : 'bg-[#f6f8fa] text-[#666d80] border-[#cdd2d9]'
            }`}
          >
            {isTurbo ? '⚡ Turbo 2.2x' : '1x Cruise'}
          </span>
          <span className="text-[9px] text-[#818898] mt-0.5">
            {isTurbo ? 'Shift Active' : 'Hold Shift: Turbo'}
          </span>
        </div>
      </div>

      {/* Flight Key Hints Banner */}
      <div className="bg-white/90 backdrop-blur-xs border border-[#cdd2d9] rounded-[8px] px-2.5 py-1 shadow-2xs flex items-center space-x-2 text-[10px] text-[#666d80] pointer-events-auto">
        <span className="w-1.5 h-1.5 rounded-full bg-[#5e4cff]" />
        <span>
          <kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded border border-[#cdd2d9] text-[#36394a]">WASD</kbd> fly ·{' '}
          <kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded border border-[#cdd2d9] text-[#36394a]">Q</kbd>/<kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded border border-[#cdd2d9] text-[#36394a]">E</kbd> alt ·{' '}
          <kbd className="font-mono bg-[#f6f8fa] px-1 py-0.5 rounded border border-[#cdd2d9] text-[#36394a]">Shift</kbd> turbo
        </span>
      </div>
    </div>
  );
};
