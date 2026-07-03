import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useAuth } from './useAuth';

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface LoginFormData {
  email: string;
  password: string;
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const returnPath = (location.state as { from?: string })?.from ?? '/';

  const [serverError, setServerError] = useState<string | null>(null);
  const [showOTP, setShowOTP] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>();

  const onSubmit = async (data: LoginFormData) => {
    setServerError(null);
    try {
      const res = await fetch(`${BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: data.email, password: data.password }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setServerError(body?.detail ?? `Login failed (${res.status})`);
        return;
      }

      const { access_token } = await res.json();
      login(access_token);
      navigate(returnPath, { replace: true });
    } catch {
      setServerError('Network error. Please try again.');
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Sign In</h1>
        <p style={styles.subtitle}>Welcome back to MentorMan</p>

        {serverError && <div style={styles.error}>{serverError}</div>}

        {!showOTP ? (
          <>
            <form onSubmit={handleSubmit(onSubmit)} style={styles.form}>
              <div style={styles.field}>
                <label style={styles.label} htmlFor="email">Email</label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  style={styles.input}
                  {...register('email', {
                    required: 'Email is required',
                    pattern: {
                      value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                      message: 'Please enter a valid email address',
                    },
                  })}
                />
                {errors.email && (
                  <span style={styles.fieldError}>{errors.email.message}</span>
                )}
              </div>

              <div style={styles.field}>
                <label style={styles.label} htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  style={styles.input}
                  {...register('password', {
                    required: 'Password is required',
                  })}
                />
                {errors.password && (
                  <span style={styles.fieldError}>{errors.password.message}</span>
                )}
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  ...styles.submitBtn,
                  opacity: isSubmitting ? 0.6 : 1,
                }}
              >
                {isSubmitting ? 'Signing in...' : 'Sign In'}
              </button>
            </form>

            <div style={styles.divider}>
              <span style={styles.dividerText}>or</span>
            </div>

            <button
              type="button"
              onClick={() => setShowOTP(true)}
              style={styles.otpToggle}
            >
              Sign in with email code (OTP)
            </button>

            <div style={styles.oauthSection}>
              <a href={`${BASE}/api/auth/oauth/google`} style={styles.oauthBtn}>
                Continue with Google
              </a>
              <a href={`${BASE}/api/auth/oauth/github`} style={styles.oauthBtn}>
                Continue with GitHub
              </a>
            </div>
          </>
        ) : (
          <OTPSection
            onBack={() => setShowOTP(false)}
            onSuccess={(token) => {
              login(token);
              navigate(returnPath, { replace: true });
            }}
          />
        )}

        <p style={styles.footer}>
          Don't have an account?{' '}
          <Link to="/register" style={styles.link}>
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}

/* ---------- OTP Section (inline) ---------- */

function OTPSection({
  onBack,
  onSuccess,
}: {
  onBack: () => void;
  onSuccess: (token: string) => void;
}) {
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [otpError, setOtpError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const requestOTP = async () => {
    setOtpError(null);
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setOtpError('Please enter a valid email address');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/auth/otp/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setOtpError(body?.detail ?? 'Failed to send code');
        return;
      }
      setStep('code');
    } catch {
      setOtpError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const verifyOTP = async () => {
    setOtpError(null);
    if (!code || code.length !== 6) {
      setOtpError('Please enter the 6-digit code');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, code }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setOtpError(body?.detail ?? 'Invalid or expired code');
        return;
      }
      const { access_token } = await res.json();
      onSuccess(access_token);
    } catch {
      setOtpError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.form}>
      {otpError && <div style={styles.error}>{otpError}</div>}

      {step === 'email' ? (
        <>
          <div style={styles.field}>
            <label style={styles.label} htmlFor="otp-email">Email</label>
            <input
              id="otp-email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
            />
          </div>
          <button
            type="button"
            onClick={requestOTP}
            disabled={loading}
            style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
          >
            {loading ? 'Sending...' : 'Send Code'}
          </button>
        </>
      ) : (
        <>
          <div style={styles.field}>
            <label style={styles.label} htmlFor="otp-code">6-digit code sent to {email}</label>
            <input
              id="otp-code"
              type="text"
              inputMode="numeric"
              maxLength={6}
              placeholder="000000"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              style={styles.input}
            />
          </div>
          <button
            type="button"
            onClick={verifyOTP}
            disabled={loading}
            style={{ ...styles.submitBtn, opacity: loading ? 0.6 : 1 }}
          >
            {loading ? 'Verifying...' : 'Verify Code'}
          </button>
        </>
      )}

      <button type="button" onClick={onBack} style={styles.backBtn}>
        ← Back to password login
      </button>
    </div>
  );
}

/* ---------- Styles ---------- */

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: '#08080a',
    padding: 16,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    background: '#111113',
    borderRadius: 12,
    padding: 32,
    border: '1px solid #222',
  },
  title: {
    color: '#fff',
    fontSize: 24,
    fontWeight: 700,
    margin: '0 0 4px',
  },
  subtitle: {
    color: '#888',
    fontSize: 14,
    margin: '0 0 24px',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  label: {
    color: '#ccc',
    fontSize: 13,
    fontWeight: 500,
  },
  input: {
    padding: '10px 12px',
    borderRadius: 8,
    border: '1px solid #333',
    background: '#1a1a1d',
    color: '#fff',
    fontSize: 14,
    outline: 'none',
  },
  fieldError: {
    color: '#f87171',
    fontSize: 12,
    marginTop: 2,
  },
  error: {
    background: '#2d1515',
    border: '1px solid #5c2020',
    color: '#f87171',
    borderRadius: 8,
    padding: '10px 12px',
    fontSize: 13,
    marginBottom: 8,
  },
  submitBtn: {
    padding: '10px 16px',
    borderRadius: 8,
    border: 'none',
    background: 'var(--accent)',
    color: 'var(--accent-ink-2)',
    fontWeight: 600,
    fontSize: 14,
    cursor: 'pointer',
    marginTop: 4,
  },
  divider: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    margin: '16px 0',
  },
  dividerText: {
    color: '#666',
    fontSize: 13,
    flexShrink: 0,
  },
  otpToggle: {
    padding: '10px 16px',
    borderRadius: 8,
    border: '1px solid #333',
    background: 'transparent',
    color: '#ccc',
    fontSize: 14,
    cursor: 'pointer',
    textAlign: 'center' as const,
  },
  oauthSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    marginTop: 12,
  },
  oauthBtn: {
    display: 'block',
    padding: '10px 16px',
    borderRadius: 8,
    border: '1px solid #333',
    background: '#1a1a1d',
    color: '#ccc',
    fontSize: 14,
    textDecoration: 'none',
    textAlign: 'center' as const,
    cursor: 'pointer',
  },
  backBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--accent)',
    fontSize: 13,
    cursor: 'pointer',
    marginTop: 8,
    padding: 0,
    textAlign: 'left' as const,
  },
  footer: {
    color: '#888',
    fontSize: 13,
    textAlign: 'center' as const,
    marginTop: 24,
    marginBottom: 0,
  },
  link: {
    color: 'var(--accent)',
    textDecoration: 'none',
  },
};
