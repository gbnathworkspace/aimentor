import { BrowserRouter, Routes, Route } from 'react-router-dom';
import {
  ClerkProvider,
  ClerkLoaded,
  ClerkLoading,
  SignedIn,
  SignedOut,
  RedirectToSignIn,
  SignIn,
  SignUp,
} from '@clerk/clerk-react';
import { MentorManApp } from './components/mentorman/app';

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;

if (!PUBLISHABLE_KEY) {
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY');
}

function centered(children: React.ReactNode) {
  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {children}
    </div>
  );
}

export default function App() {
  return (
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <BrowserRouter>
        <Routes>
          <Route
            path="/sign-in/*"
            element={centered(
              <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />,
            )}
          />
          <Route
            path="/sign-up/*"
            element={centered(
              <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" />,
            )}
          />
          <Route
            path="/*"
            element={
              <>
                <ClerkLoading>
                  <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#08080a' }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', border: '3px solid #34d399', borderTopColor: 'transparent', animation: 'spin 0.7s linear infinite' }} />
                  </div>
                </ClerkLoading>
                <SignedIn>
                  {/* ClerkLoaded guarantees window.Clerk.session is ready before
                      the app's data-fetching effects run. */}
                  <ClerkLoaded>
                    <MentorManApp />
                  </ClerkLoaded>
                </SignedIn>
                <SignedOut>
                  <RedirectToSignIn />
                </SignedOut>
              </>
            }
          />
        </Routes>
      </BrowserRouter>
    </ClerkProvider>
  );
}
