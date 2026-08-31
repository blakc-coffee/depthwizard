import { NavLink } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export const Header = () => {
  const { user, signOut } = useAuth();

  return (
    <header className="bg-[#FDFCF8] border-b border-gray-200 sticky top-0 z-30 shadow-sm max-w-full overflow-hidden">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center space-x-3 sm:space-x-6 min-w-0">
            <NavLink
              to="/app"
              className="flex items-center space-x-2 text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-600 rounded-md py-1 px-1 flex-shrink-0"
            >
              <span className="w-7 h-7 rounded-md bg-purple-700 text-white font-bold flex items-center justify-center text-sm shadow-sm">
                D
              </span>
              <span className="text-lg sm:text-xl font-bold tracking-tight text-gray-900">
                DepthWizard
              </span>
              <span className="text-xs bg-[#ECE9DD] text-gray-700 px-2 py-0.5 rounded font-mono hidden sm:inline-block">
                Spatial 3D
              </span>
            </NavLink>

            <nav aria-label="Main Navigation" className="hidden md:flex space-x-1">
              <NavLink
                to="/app"
                end
                className={({ isActive }) =>
                  `px-3 py-2 rounded-md text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-600 ${
                    isActive
                      ? 'bg-[#ECE9DD] text-purple-900 font-semibold'
                      : 'text-gray-700 hover:text-purple-700 hover:bg-[#ECE9DD]/50'
                  }`
                }
              >
                Workspace
              </NavLink>
            </nav>
          </div>

          <div className="flex items-center space-x-2 sm:space-x-4 flex-shrink-0">
            {user && (
              <span className="text-xs font-mono text-gray-600 truncate max-w-[100px] xs:max-w-[160px] sm:max-w-[240px]">
                {user.email}
              </span>
            )}
            <button
              type="button"
              onClick={() => signOut()}
              className="bg-[#FDFCF8] hover:bg-[#ECE9DD] border border-gray-300 text-gray-800 text-xs sm:text-sm font-medium px-2.5 sm:px-3.5 py-1.5 rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-600 transition-colors"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
