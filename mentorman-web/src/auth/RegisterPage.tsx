import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from './useAuth';

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

interface RegisterFormData {
  email: string;
  password: string;
}

export function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormData>();

  const onSubmit = async (data: RegisterFormData) => {
    setServerError(null);

    try {
      const res = await fetch(`${BASE}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email, password: data.password }),
        credentials: 'include',
      });

      if (res.ok) {
        const body = await res.json();
        login(body.access_token);
        navigate('/', { replace: true });
        return;
      }

      if (res.status === 409) {
        setServerError('An account with this email already exists.');
        return;
      }

      if (res.status === 422) {
        const body = await res.json();
        const detail = body.detail;
        if (Array.isArray(detail)) {
          setServerError(detail.map((e: { msg?: string }) => e.msg ?? '').join('. '));
        } else if (typeof detail === 'string') {
          setServerError(detail);
        } else {
          setServerError('Validation error. Please check your input.');
        }
        return;
      }

      setServerError('Something went wrong. Please try again.');
    } catch {
      setServerError('Network error. Please check your connection.');
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>Create Account</h1>
        <p style={styles.subtitle}>Sign up to get started</p>

        <form onSubmit={handleSubmit(onSubmit)} noValidate style={styles.form}>
          {serverError && <div style={styles.serverError}>{serverError}</div>}

          <div style={styles.field}>
            <label htmlFor="email" style={styles.label}>Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              style={{
                ...styles.input,
                ...(errors.email ? styles.inputError : {}),
              }}
              {...register('email', {
                required: 'Email is required',
                pattern: {
                  value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
                  message: 'Enter a valid email address',
                },
              })}
            />
            {errors.email && (
              <span style={styles.errorText}>{errors.email.message}</span>
            )}
          </div>

          <div style={styles.field}>
            <label htmlFor="password" style={styles.label}>Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              style={{
                ...styles.input,
                ...(errors.password ? styles.inputError : {}),
              }}
              {...register('password', {
                required: 'Password is required',
                minLength: {
                  value: 8,
                  message: 'Password must be at least 8 characters',
                },
                maxLength: {
                  value: 128,
                  message: 'Password must be at most 128 characters',
                },
              })}
            />
            {errors.password && (
              <span style={styles.errorText}>{errors.password.message}</span>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            style={{
              ...styles.button,
              ...(isSubmitting ? styles.buttonDisabled : {}),
            }}
          >
            {isSubmitting ? 'Creating account...' : 'Create Account'}
          </button>
        </form>

        <p style={styles.footer}>
          Already have an account?{' '}
          <Link to="/login" style={styles.link}>Sign in</Link>
        </p>
      </div>
    </div>
  );
}

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
    padding: 32,
    borderRadius: 12,
    background: '#111113',
    border: '1px solid #222',
  },
  title: {
    margin: 0,
    fontSize: 24,
    fontWeight: 600,
    color: '#ffffff',
  },
  subtitle: {
    margin: '8px 0 24px',
    fontSize: 14,
    color: '#888',
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
    fontSize: 14,
    fontWeight: 500,
    color: '#ccc',
  },
  input: {
    padding: '10px 12px',
    fontSize: 14,
    borderRadius: 8,
    border: '1px solid #333',
    background: '#1a1a1e',
    color: '#fff',
    outline: 'none',
  },
  inputError: {
    borderColor: '#ef4444',
  },
  errorText: {
    fontSize: 12,
    color: '#ef4444',
    marginTop: 2,
  },
  serverError: {
    padding: '10px 12px',
    borderRadius: 8,
    background: 'rgba(239, 68, 68, 0.1)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    color: '#ef4444',
    fontSize: 13,
  },
  button: {
    marginTop: 8,
    padding: '12px 16px',
    fontSize: 14,
    fontWeight: 600,
    borderRadius: 8,
    border: 'none',
    background: '#34d399',
    color: '#08080a',
    cursor: 'pointer',
  },
  buttonDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  footer: {
    marginTop: 20,
    textAlign: 'center',
    fontSize: 14,
    color: '#888',
  },
  link: {
    color: '#34d399',
    textDecoration: 'none',
  },
};
