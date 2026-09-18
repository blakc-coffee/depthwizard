import { NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export const Header = () => {
  const { user, signOut } = useAuth();
  const location = useLocation();

  const isInputPage = location.pathname === '/app' || location.pathname === '/silt';
  const isSilt = location.pathname === '/silt';

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

        {/* Use-case switcher — Exists strictly on input pages (/app, /silt) */}
        {isInputPage && (
          <div className="flex items-center bg-[#f4f5f7] rounded-md p-1 text-xs font-medium space-x-1">
            <NavLink
              to="/app"
              className={`px-3 py-1.5 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] ${
                !isSilt
                  ? 'bg-[#5e4cff] text-white shadow-xs font-medium'
                  : 'text-[#666d80] hover:text-[#36394a] hover:bg-black/5 font-medium'
              }`}
            >
              Terrain
            </NavLink>
            <NavLink
              to="/silt"
              className={`px-3 py-1.5 rounded-md transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#5e4cff] ${
                isSilt
                  ? 'bg-[#5e4cff] text-white shadow-xs font-medium'
                  : 'text-[#666d80] hover:text-[#36394a] hover:bg-black/5 font-medium'
              }`}
            >
              River Silt
            </NavLink>
          </div>
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
