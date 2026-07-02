import { useState, FormEvent } from 'react';
import { useAuth } from './useAuth';

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface OTPFormProps {
  onSuccess: () => void;
}

export function OTPForm({ onSuccess }: OTPFormProps) {
  const { login } = useAuth();

  // Step 1: email input, Step 2: code input
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleRequestOTP(e: FormEvent) {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const res = await fetch(`${BASE}/api/auth/otp/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (res.ok) {
        setMessage('A 6-digit code has been sent to your email.');
        setStep(2);
      } else if (res.status === 429) {
        setError('Too many requests. Please try again later.');
      } else {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? 'Failed to send code. Please try again.');
      }
    } catch {
      setError('Network error. Please check your connection.');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOTP(e: FormEvent) {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);

    try {
      const res = await fetch(`${BASE}/api/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, code }),
      });

      if (res.ok) {
        const data = await res.json();
        login(data.access_token);
        onSuccess();
      } else if (res.status === 429) {
        setError('Too many attempts. Please try again later.');
      } else if (res.status === 401) {
        setError('Invalid or expired code. Please try again.');
      } else {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? 'Verification failed. Please try again.');
      }
    } catch {
      setError('Network error. Please check your connection.');
    } finally {
      setLoading(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 12px',
    background: 'transparent',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#fff',
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  };

  const buttonStyle: React.CSSProperties = {
    width: '100%',
    padding: '10px 16px',
    background: '#34d399',
    color: '#000',
    border: 'none',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: 600,
    cursor: loading ? 'not-allowed' : 'pointer',
    opacity: loading ? 0.7 : 1,
  };

  if (step === 1) {
    return (
      <form onSubmit={handleRequestOTP} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label style={{ color: '#9ca3af', fontSize: 13 }}>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            placeholder="you@example.com"
            style={{ ...inputStyle, marginTop: 4 }}
          />
        </label>

        {error && (
          <p style={{ color: '#f87171', fontSize: 13, margin: 0 }}>{error}</p>
        )}

        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? 'Sending...' : 'Send Code'}
        </button>
      </form>
    );
  }

  return (
    <form onSubmit={handleVerifyOTP} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {message && (
        <p style={{ color: '#34d399', fontSize: 13, margin: 0 }}>{message}</p>
      )}

      <label style={{ color: '#9ca3af', fontSize: 13 }}>
        6-digit code
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          required
          pattern="\d{6}"
          maxLength={6}
          placeholder="000000"
          inputMode="numeric"
          autoComplete="one-time-code"
          style={{ ...inputStyle, marginTop: 4, letterSpacing: '0.2em', textAlign: 'center' }}
        />
      </label>

      {error && (
        <p style={{ color: '#f87171', fontSize: 13, margin: 0 }}>{error}</p>
      )}

      <button type="submit" disabled={loading} style={buttonStyle}>
        {loading ? 'Verifying...' : 'Verify Code'}
      </button>

      <button
        type="button"
        onClick={() => {
          setStep(1);
          setCode('');
          setError('');
          setMessage('');
        }}
        style={{
          background: 'transparent',
          border: 'none',
          color: '#9ca3af',
          fontSize: 13,
          cursor: 'pointer',
          textDecoration: 'underline',
        }}
      >
        Use a different email
      </button>
    </form>
  );
}
