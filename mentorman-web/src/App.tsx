import { BrowserRouter, Routes, Route } from 'react-router-dom';
import {
  ClerkProvider,
  ClerkLoaded,
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
