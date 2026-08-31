import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export const Header = () => {
  const { user, signOut } = useAuth();
  const location = useLocation();

  const isAuthPage = location.pathname === '/login';
  const isInput = location.pathname === '/app' || location.pathname === '/';
  const isProcessing = location.pathname.startsWith('/processing');
  const isResults = location.pathname.startsWith('/results');

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

        {/* Workflow Navigation - ONLY displayed on authenticated app pages */}
        {!isAuthPage && (
          <nav aria-label="Main Navigation" className="hidden sm:flex items-center space-x-8 text-xs font-medium">
            <NavLink
              to="/app"
              className={`transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] rounded py-1 px-1.5 ${
                isInput ? 'text-[#5e4cff] font-semibold' : 'text-[#666d80] hover:text-[#36394a]'
              }`}
            >
              Input
            </NavLink>

            <span
              className={`transition-colors ${
                isProcessing ? 'text-[#5e4cff] font-semibold' : 'text-[#666d80]'
              }`}
            >
              Processing
            </span>

            <span
              className={`transition-colors ${
                isResults ? 'text-[#5e4cff] font-semibold' : 'text-[#818898]'
              }`}
            >
              Results
            </span>
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
