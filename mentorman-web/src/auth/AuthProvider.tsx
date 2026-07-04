import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  ReactNode,
} from 'react';
import { setTokenSource } from '../api/client';
import { configureApiClient } from './api-client';

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface AuthContextType {
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
  refresh: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const tokenRef = useRef<string | null>(null);

  // Keep ref in sync with state so the getter always returns current value
  tokenRef.current = accessToken;

  const refresh = useCallback(async (): Promise<string | null> => {
    try {
      const res = await fetch(`${BASE}/api/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        setAccessToken(null);
        return null;
      }
      const data = await res.json();
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      setAccessToken(null);
      return null;
    }
  }, []);

  const login = useCallback((token: string) => {
    setAccessToken(token);
  }, []);

  const logout = useCallback(async () => {
    setAccessToken(null);
    try {
      await fetch(`${BASE}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch {
      // Logout endpoint failure is non-critical; token is already cleared
    }
  }, []);

  // Wire up legacy fetch shim and new api-client with token access
  useEffect(() => {
    const getToken = () => tokenRef.current;
    setTokenSource(getToken);
    configureApiClient(getToken, refresh, logout);
  }, [refresh, logout]);

  // On mount, attempt silent refresh (refresh token in HTTP-only cookie)
  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  // Best-effort skill checkpoint on tab/browser close — pagehide only fires on
  // real page teardown (close/navigate-away), not SPA route changes or tab
  // backgrounding. sendBeacon (not fetch) survives the page unload.
  useEffect(() => {
    const onPageHide = () => {
      if (tokenRef.current) navigator.sendBeacon(`${BASE}/api/auth/checkpoint`);
    };
    window.addEventListener('pagehide', onPageHide);
    return () => window.removeEventListener('pagehide', onPageHide);
  }, []);

  if (loading) {
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#08080a',
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            border: '3px solid var(--accent)',
            borderTopColor: 'transparent',
            animation: 'spin 0.7s linear infinite',
          }}
        />
      </div>
    );
  }

  return (
    <AuthContext.Provider
      value={{
        accessToken,
        isAuthenticated: !!accessToken,
        login,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
