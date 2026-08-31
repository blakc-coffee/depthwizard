import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { useAuth } from '../hooks/useAuth';

export const AuthPage = () => {
  const { user, loading } = useAuth();

  useEffect(() => {
    document.title = 'DepthWizard | Sign In';
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#F6F4EC] flex items-center justify-center p-4">
        <div className="flex items-center space-x-3 text-gray-700 text-sm font-medium">
          <svg
            className="animate-spin h-5 w-5 text-purple-700"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Checking session...</span>
        </div>
      </div>
    );
  }

  if (user) {
    return <Navigate to="/app" replace />;
  }

  return (
    <div className="min-h-screen bg-[#F6F4EC] flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <AuthPageHeader />
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md px-4">
        <LoginForm />
      </div>
    </div>
  );
};

const AuthPageHeader = () => {
  return (
    <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
      <div className="inline-flex items-center space-x-2.5 mb-2">
        <span className="w-8 h-8 rounded-lg bg-purple-700 text-white font-bold flex items-center justify-center text-lg shadow-sm">
          D
        </span>
        <span className="text-2xl font-bold tracking-tight text-gray-900">DepthWizard</span>
      </div>
      <p className="text-xs font-mono text-gray-500 uppercase tracking-wider">
        SIH 2026 • Single-View Terrain 3D
      </p>
    </div>
  );
};
