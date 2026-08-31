import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export const LoginForm = () => {
  const { signInWithPassword, signUp } = useAuth();
  const navigate = useNavigate();

  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!email.trim() || !password.trim()) {
      setErrorMessage('Please enter both email address and password.');
      return;
    }

    setSubmitting(true);

    try {
      const { error } = isSignUp
        ? await signUp(email, password)
        : await signInWithPassword(email, password);

      if (error) {
        setErrorMessage(error.message || 'Authentication failed. Please check your credentials.');
        setSubmitting(false);
        return;
      }

      navigate('/app', { replace: true });
    } catch {
      setErrorMessage('An unexpected error occurred during authentication.');
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-[440px]">
      <div className="bg-white border border-[#cdd2d9] rounded-[12px] p-6 sm:p-7">
        <div className="mb-5">
          <h2 className="text-xl font-semibold tracking-tight text-[#36394a] font-heading mb-1">
            {isSignUp ? 'Create DepthWizard Account' : 'Sign in to DepthWizard'}
          </h2>
          <p className="text-xs text-[#666d80]">
            {isSignUp
              ? 'Enter your credentials to register a new spatial workspace.'
              : 'Single-view height estimation and 3D terrain reconstruction.'}
          </p>
        </div>

        {errorMessage && (
          <div
            role="alert"
            aria-live="polite"
            className="mb-5 bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] text-xs rounded-md p-3 flex items-start space-x-2"
          >
            <svg
              className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-[#666d80] mb-1.5 font-sans">
              Email address
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com..."
              className="w-full bg-white border border-[#cdd2d9] rounded-[8px] px-3.5 py-2 text-sm text-[#36394a] placeholder-[#818898] focus:outline-none focus:ring-2 focus:ring-[#5e4cff] focus:border-transparent transition-colors"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-medium text-[#666d80] mb-1.5 font-sans">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={isSignUp ? 'new-password' : 'current-password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-white border border-[#cdd2d9] rounded-[8px] px-3.5 py-2 text-sm text-[#36394a] placeholder-[#818898] focus:outline-none focus:ring-2 focus:ring-[#5e4cff] focus:border-transparent transition-colors"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-[#5e4cff] hover:bg-[#5e4cff]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 px-4 rounded-[8px] focus:outline-none focus:ring-2 focus:ring-[#5e4cff] focus:ring-offset-2 transition-colors flex items-center justify-center space-x-2 text-sm"
            >
              {submitting && (
                <svg
                  className="animate-spin h-4 w-4 text-white"
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
              )}
              <span>{isSignUp ? 'Sign Up' : 'Sign In'}</span>
            </button>
          </div>
        </form>

        <div className="mt-4 pt-4 border-t border-[#cdd2d9] flex justify-between items-center text-xs">
          <span className="text-[#818898]">Secure session via Supabase Auth</span>
          <button
            type="button"
            onClick={() => {
              setIsSignUp(!isSignUp);
              setErrorMessage(null);
            }}
            className="font-medium text-[#5e4cff] hover:text-[#5e4cff]/80 focus:outline-none focus:underline"
          >
            {isSignUp ? 'Sign In' : 'Create account'}
          </button>
        </div>
      </div>
    </div>
  );
};
