export const Footer = () => {
  return (
    <footer className="w-full border-t border-gray-200 bg-[#FDFCF8] py-6 px-4 mt-auto text-center text-xs text-gray-500">
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-gray-700">DepthWizard</span>
          <span>•</span>
          <span>Single-View Height Estimation & 3D Terrain Reconstruction</span>
        </div>
        <div className="font-mono text-gray-400">
          SIH 2026 • Depth Anything V2 + SRTM Reference Calibration
        </div>
      </div>
    </footer>
  );
};
