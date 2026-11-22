import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { trackScreen } from './lib/analytics';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { LoginPage } from './auth/LoginPage';
import { RegisterPage } from './auth/RegisterPage';
import { OAuthCallback } from './auth/OAuthCallback';
import { MentorManApp } from './components/mentorman/app';
import { LandingPage } from './marketing/LandingPage';
import { useAuth } from './auth/useAuth';

// Screens outside the signed-in app (landing, login, register) are real URLs,
// so they are tracked by route. The signed-in app tracks its own screens.
function PublicRouteTracker() {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  useEffect(() => {
    if (pathname === '/' && !isAuthenticated) trackScreen('landing');
    else if (pathname === '/login') trackScreen('login');
    else if (pathname === '/register') trackScreen('register');
  }, [pathname, isAuthenticated]);
  return null;
}

function Home() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <MentorManApp /> : <LandingPage />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <PublicRouteTracker />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/auth/callback" element={<OAuthCallback />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <MentorManApp />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
