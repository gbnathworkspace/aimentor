// ─── API fetch shim ─────────────────────────────────────────────────────────
// Installs a global fetch interceptor so the (frozen) UI keeps calling
// `fetch('/api/...')` unchanged. For those calls the shim:
//   1. Rewrites the URL to the FastAPI base (VITE_API_BASE; '' in same-origin prod).
//   2. Attaches the session JWT as `Authorization: Bearer`.
//   3. Normalizes response bodies to carry BOTH snake_case and camelCase keys, so
//      components reading either casing (the DB/UI mix snake for profile/skills and
//      camel for sessions) all resolve.
//   4. Synthesizes `/api/me` from the configured user info getter.
//
// Uses fetch (not EventSource) so SSE streaming can be layered on later.

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

// ─── Configurable token source ──────────────────────────────────────────────
// AuthProvider calls setTokenSource() on mount to wire up token retrieval.
let _tokenGetter: () => string | null = () => null;
let _refresh: () => Promise<string | null> = async () => null;
let _logout: () => void = () => {};

/**
 * Set the function used to retrieve the current access token.
 * Called by AuthProvider to bridge the auth system with the legacy fetch shim.
 */
export function setTokenSource(getter: () => string | null): void {
  _tokenGetter = getter;
}

/**
 * Wire up refresh/logout so the shim can recover from an expired access
 * token instead of leaving every /api/* call 401ing until the next reload.
 */
export function setAuthHandlers(refresh: () => Promise<string | null>, logout: () => void): void {
  _refresh = refresh;
  _logout = logout;
}

function getToken(): string | null {
  return _tokenGetter();
}

const toSnake = (k: string): string => k.replace(/[A-Z]/g, (m) => '_' + m.toLowerCase());
const toCamel = (k: string): string => k.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

// Recursively duplicate every object key into both snake_case and camelCase.
function withBothCasings(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withBothCasings);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      const nv = withBothCasings(v);
      out[toSnake(k)] = nv;
      out[toCamel(k)] = nv;
    }
    return out;
  }
  return value;
}

// ─── Per-endpoint response adapters ───────────────────────────────────────────
// Some Next.js routes reshaped responses for the UI (semantic renames the casing
// adapter can't reproduce). Reproduce those exact shapes here so the frozen UI
// keeps working against the generic FastAPI contract. Input is already dual-cased.
type AnyObj = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function adaptResponse(path: string, data: unknown): unknown {
  const p = path.split('?')[0];

  // GET /api/sessions → sidebar shape: { session_id, title, type, topic, topic_category, date, summary }
  if (p === '/api/sessions' && Array.isArray(data)) {
    return data.map((s: AnyObj) => ({
      ...s,
      session_id: s.session_id ?? s.sessionId,
      title: s.title,
      type: s.mode ?? s.type ?? 'Topic',
      topic: s.topic ?? '',
      topic_category: Array.isArray(s.tags) ? (s.tags[0] ?? '') : (s.topic_category ?? ''),
      date: s.created_at ?? s.createdAt ?? '',
      summary: s.summary ?? '',
    }));
  }

  return data;
}

// ─── /api/me handler ────────────────────────────────────────────────────────
// With the self-hosted auth system, /api/me is fetched from the backend.
// If the backend doesn't support it yet, we return a minimal fallback.
let _realFetch: typeof window.fetch | null = null;

async function meResponse(): Promise<Response> {
  // Try fetching from the backend
  if (_realFetch) {
    const token = getToken();
    const headers: HeadersInit = {};
    if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
    try {
      const res = await _realFetch(`${BASE}/api/me`, { headers });
      if (res.ok) return res;
    } catch {
      // Fall through to fallback
    }
  }

  // Fallback: return a generic user object
  return new Response(JSON.stringify({ name: 'User', email: '' }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

export function installApiFetch(): void {
  const realFetch = window.fetch.bind(window);
  _realFetch = realFetch;

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (!url.startsWith('/api/')) {
      return realFetch(input as RequestInfo | URL, init);
    }

    // /api/me → handled specially
    if (url === '/api/me' || url.startsWith('/api/me?')) {
      return meResponse();
    }

    const token = getToken();
    const headers = new Headers(
      init?.headers ??
        (typeof input === 'object' && 'headers' in input ? (input as Request).headers : undefined),
    );
    if (token) headers.set('Authorization', `Bearer ${token}`);

    let res = await realFetch(`${BASE}${url}`, { ...init, headers });

    // On 401, attempt one silent refresh + retry (except for the auth
    // endpoints themselves, to avoid recursing into a retry loop).
    const path = url.split('?')[0];
    if (res.status === 401 && path !== '/api/auth/refresh' && path !== '/api/auth/logout') {
      const newToken = await _refresh();
      if (newToken) {
        headers.set('Authorization', `Bearer ${newToken}`);
        res = await realFetch(`${BASE}${url}`, { ...init, headers });
      } else {
        _logout();
      }
    }

    // Patch json(): dual-case, then apply any per-endpoint shape adapter.
    const originalJson = res.json.bind(res);
    (res as Response & { json: () => Promise<unknown> }).json = async () =>
      adaptResponse(path, withBothCasings(await originalJson()));

    return res;
  };
}

export { withBothCasings };
