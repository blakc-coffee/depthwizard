import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { LoginForm } from '../components/auth/LoginForm';
import { Header } from '../components/layout/Header';
import { useAuth } from '../hooks/useAuth';

export const AuthPage = () => {
  const { user, loading } = useAuth();

  useEffect(() => {
    document.title = 'DepthWizard | Sign In';
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-4">
        <div className="flex items-center space-x-3 text-[#36394a] text-sm font-medium">
          <svg
            className="animate-spin h-5 w-5 text-[#5e4cff]"
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
    <div className="relative min-h-screen bg-white text-[#36394a] font-sans flex flex-col justify-between antialiased w-full overflow-x-hidden">
      <div className="w-full px-6 sm:px-10 lg:px-12 py-4 flex flex-col flex-1 box-border">
        {/* Seamless Header (DEPTHWIZARD + Sign In only on auth page) */}
        <Header />

        {/* Top-Anchored Left-Aligned Hero Section */}
        <div className="pt-2 sm:pt-6 lg:pt-8 pb-16 w-full max-w-2xl flex flex-col items-start space-y-6 lg:space-y-8">
          <h1 className="text-[36px] sm:text-[44px] lg:text-[52px] font-semibold tracking-tight text-[#36394a] font-heading leading-[1.12]">
            Reconstruct terrain from
            <br className="hidden sm:inline" /> a single image.
          </h1>

          <LoginForm />
        </div>
      </div>

      {/* Tiny Bottom-Right Corner Decorative Pixel Grid Motif Signature */}
      <div
        aria-hidden="true"
        className="hidden lg:block absolute bottom-8 lg:bottom-10 right-8 lg:right-16 pointer-events-none select-none z-10"
      >
        <PixelGridMotif />
      </div>
    </div>
  );
};

const PixelGridMotif = () => {
  // Small discrete raw pixel grid signature anchored to bottom-right corner
  const pixels = [
    { size: 'w-5 h-5', color: 'bg-[#5e4cff]', opacity: 'opacity-90' },
    { size: 'w-3 h-3', color: 'bg-[#c8ccf3]', opacity: 'opacity-80' },
    { size: 'w-4 h-4', color: 'bg-[#5e4cff]', opacity: 'opacity-70' },
    { size: 'w-3 h-3', color: 'bg-[#dfdbff]', opacity: 'opacity-60' },
    { size: 'w-3.5 h-3.5', color: 'bg-[#5e4cff]', opacity: 'opacity-80' },
    { size: 'w-3 h-3', color: 'bg-[#c8ccf3]', opacity: 'opacity-90' },
    { size: 'w-5 h-5', color: 'bg-[#5e4cff]', opacity: 'opacity-100' },
    { size: 'w-3.5 h-3.5', color: 'bg-[#c8ccf3]', opacity: 'opacity-70' },
    { size: 'w-4 h-4', color: 'bg-[#dfdbff]', opacity: 'opacity-90' },
    { size: 'w-3 h-3', color: 'bg-[#5e4cff]', opacity: 'opacity-100' },
    { size: 'w-6 h-6', color: 'bg-[#dfdbff]', opacity: 'opacity-80' },
    { size: 'w-3.5 h-3.5', color: 'bg-[#c8ccf3]', opacity: 'opacity-90' },
    { size: 'w-3 h-3', color: 'bg-[#5e4cff]', opacity: 'opacity-80' },
    { size: 'w-4 h-4', color: 'bg-[#c8ccf3]', opacity: 'opacity-100' },
    { size: 'w-3 h-3', color: 'bg-[#5e4cff]', opacity: 'opacity-70' },
  ];

  return (
    <div className="grid grid-cols-5 gap-2.5 items-center justify-items-center opacity-85">
      {pixels.map((p, idx) => (
        <div
          key={idx}
          className={`${p.size} ${p.color} ${p.opacity} rounded-xs`}
        />
      ))}
    </div>
  );
};
