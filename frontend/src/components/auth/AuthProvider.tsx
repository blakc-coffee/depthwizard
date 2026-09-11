import React, { createContext, useContext, useEffect, useState } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { supabase } from '../../lib/supabase';

interface AuthContextType {
  session: Session | null;
  user: User | null;
  loading: boolean;
  signInWithPassword: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUp: (email: string, password: string) => Promise<{ error: Error | null }>;
  signOut: () => Promise<{ error: Error | null }>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const MOCK_STORAGE_KEY = 'depthwizard_mock_session';

function checkIsMockAuth(): boolean {
  if (import.meta.env.VITE_USE_MOCK_API === 'true') return true;
  try {
    return typeof window !== 'undefined' && localStorage.getItem(MOCK_STORAGE_KEY) !== null;
  } catch {
    return false;
  }
}

function createMockSession(email: string): Session {
  const mockUser: User = {
    id: 'mock-user-1234',
    app_metadata: { provider: 'email' },
    user_metadata: {},
    aud: 'authenticated',
    created_at: new Date().toISOString(),
    email: email || 'user@depthwizard.io',
    phone: '',
    role: 'authenticated',
    updated_at: new Date().toISOString(),
  };

  return {
    access_token: 'mock-access-token-xyz',
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'mock-refresh-token',
    user: mockUser,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;

    async function initAuth() {
      if (checkIsMockAuth()) {
        const savedMock = localStorage.getItem(MOCK_STORAGE_KEY);
        if (savedMock) {
          try {
            const mockSession = JSON.parse(savedMock) as Session;
            if (mounted) {
              setSession(mockSession);
              setUser(mockSession.user);
            }
          } catch {
            localStorage.removeItem(MOCK_STORAGE_KEY);
          }
        }
        if (mounted) setLoading(false);
        return;
      }

      // If mock auth is not active, clean up any stale mock session from localStorage
      localStorage.removeItem(MOCK_STORAGE_KEY);

      try {
        const { data: { session: initialSession } } = await supabase.auth.getSession();
        if (mounted) {
          setSession(initialSession);
          setUser(initialSession?.user ?? null);
        }
      } catch (err) {
        console.error('Error fetching initial auth session:', err);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }

      const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, currentSession) => {
        if (mounted) {
          setSession(currentSession);
          setUser(currentSession?.user ?? null);
          setLoading(false);
        }
      });

      return () => {
        subscription.unsubscribe();
      };
    }

    initAuth();

    return () => {
      mounted = false;
    };
  }, []);

  const signInWithPassword = async (email: string, password: string) => {
    if (checkIsMockAuth()) {
      if (!email || !password) {
        return { error: new Error('Please enter email and password.') };
      }
      const mockSession = createMockSession(email);
      setSession(mockSession);
      setUser(mockSession.user);
      localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(mockSession));
      return { error: null };
    }

    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        return { error: new Error(error.message || 'Invalid email or password.') };
      }

      setSession(data.session);
      setUser(data.user);
      return { error: null };
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Authentication service error. Please try again.';
      return { error: new Error(message) };
    }
  };

  const signUp = async (email: string, password: string) => {
    if (checkIsMockAuth()) {
      const mockSession = createMockSession(email);
      setSession(mockSession);
      setUser(mockSession.user);
      localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify(mockSession));
      return { error: null };
    }

    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
      });

      if (error) {
        return { error: new Error(error.message || 'Registration failed. Please check your details.') };
      }

      if (data.session) {
        setSession(data.session);
        setUser(data.user);
      }
      return { error: null };
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Registration failed. Please try again.';
      return { error: new Error(message) };
    }
  };

  const signOut = async () => {
    localStorage.removeItem(MOCK_STORAGE_KEY);
    setSession(null);
    setUser(null);
    try {
      await supabase.auth.signOut();
    } catch {
      // Ignore network errors on sign out
    }
    return { error: null };
  };

  return (
    <AuthContext.Provider
      value={{
        session,
        user,
        loading,
        signInWithPassword,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
