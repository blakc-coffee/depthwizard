import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export const Header = () => {
  const { user, signOut } = useAuth();
  const location = useLocation();

  const isAuthPage = location.pathname === '/login';
  const isSiltUseCase = location.pathname.startsWith('/silt');
  const isInput = location.pathname === '/app' || location.pathname === '/';
  const isProcessing = location.pathname.startsWith('/processing') || location.pathname.startsWith('/silt-processing');
  const isResults = location.pathname.startsWith('/results') || location.pathname.startsWith('/silt-results');

  const terrainTarget = isResults
    ? '/results/mock-job-1789634079774'
    : isProcessing
      ? '/processing/mock-job-1789634079774'
      : '/app';
  const siltTarget = isResults
    ? '/silt-results/real-demo'
    : isProcessing
      ? '/silt-processing/silt-job-demo'
      : '/silt';

  const inputTarget = isSiltUseCase ? '/silt' : '/app';
  const processingTarget = isSiltUseCase ? '/silt-processing/silt-job-demo' : '/processing/mock-job-1789634079774';
  const resultsTarget = isSiltUseCase ? '/silt-results/real-demo' : '/results/mock-job-1789634079774';

  return (
    <header className="w-full bg-white py-4 mb-4 sm:mb-8 flex-shrink-0">
      <div className="flex items-center justify-between">
        {/* Brand */}
        <NavLink
          to="/app"
          className="flex items-center space-x-2.5 text-[#36394a] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] rounded-md py-1 px-1 flex-shrink-0"
        >
          <span className="w-6 h-6 rounded-md bg-[#5e4cff] text-white font-bold flex items-center justify-center text-xs">
            D
          </span>
          <span className="text-sm font-bold tracking-widest uppercase text-[#36394a] font-heading">
            DEPTHWIZARD
          </span>
        </NavLink>

        {/* Use-case switcher — Square buttons without border around the button */}
        {!isAuthPage && (
          <div className="hidden sm:flex items-center bg-[#f4f5f7] rounded-md p-1 text-xs font-medium space-x-1">
            <NavLink
              to={terrainTarget}
              className={`px-3 py-1.5 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] ${
                !isSiltUseCase ? 'bg-[#5e4cff] text-white shadow-xs' : 'text-[#666d80] hover:text-[#36394a] hover:bg-black/5'
              }`}
            >
              Terrain
            </NavLink>
            <NavLink
              to={siltTarget}
              className={`px-3 py-1.5 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] ${
                isSiltUseCase ? 'bg-[#5e4cff] text-white shadow-xs' : 'text-[#666d80] hover:text-[#36394a] hover:bg-black/5'
              }`}
            >
              River Silt
            </NavLink>
          </div>
        )}

        {/* Workflow Navigation — Visible anywhere across the app */}
        {!isAuthPage && (
          <nav aria-label="Main Navigation" className="hidden sm:flex items-center space-x-8 text-xs font-medium">
            <NavLink
              to={inputTarget}
              className={`transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] rounded py-1 px-1.5 ${
                isInput ? 'text-[#5e4cff] font-semibold' : 'text-[#666d80] hover:text-[#36394a]'
              }`}
            >
              Input
            </NavLink>

            <NavLink
              to={isProcessing ? location.pathname : processingTarget}
              className={`transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] rounded py-1 px-1.5 ${
                isProcessing ? 'text-[#5e4cff] font-semibold' : 'text-[#666d80] hover:text-[#36394a]'
              }`}
            >
              Processing
            </NavLink>

            <NavLink
              to={isResults ? location.pathname : resultsTarget}
              className={`transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] rounded py-1 px-1.5 ${
                isResults ? 'text-[#5e4cff] font-semibold' : 'text-[#818898] hover:text-[#36394a]'
              }`}
            >
              Results
            </NavLink>
          </nav>
        )}

        {/* User Actions */}
        <div className="flex items-center space-x-3 flex-shrink-0">
          {user && (
            <span className="text-xs font-mono text-[#818898] truncate max-w-[120px] sm:max-w-[200px]">
              {user.email}
            </span>
          )}
          {user ? (
            <button
              type="button"
              onClick={() => signOut()}
              className="bg-white hover:bg-[#f6f8fa] border border-[#cdd2d9] text-[#36394a] text-xs font-medium px-3 py-1.5 rounded-[8px] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] transition-colors"
            >
              Sign Out
            </button>
          ) : (
            <NavLink
              to="/login"
              className="text-xs text-[#36394a] font-medium hover:text-[#5e4cff]"
            >
              Sign In
            </NavLink>
          )}
        </div>
      </div>
    </header>
  );
};
