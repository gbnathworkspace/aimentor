// ─── Backend Proxy Utility ────────────────────────────────────────────────────
// Thin proxy layer: extracts Clerk userId, attaches auth headers, and forwards
// requests to the unified FastAPI backend. All business logic lives in the
// backend — this layer only handles authentication gating and header injection.

function getApiBase(): string {
  return process.env.MENTORMAN_API_BASE ?? 'http://localhost:8000';
}

function getApiKey(): string {
  return process.env.MENTORMAN_API_KEY!;
}

/**
 * Forward a request to the unified backend with service-to-service auth headers.
 * Caller is responsible for ensuring `userId` is valid (non-empty).
 *
 * @param path   - Backend path including leading slash, e.g. `/api/profile`
 * @param userId - Authenticated Clerk userId to attach as X-User-Id
 * @param init   - Optional RequestInit (method, body, headers, etc.)
 * @returns The backend's Response object unchanged
 */
export async function proxyToBackend(
  path: string,
  userId: string,
  init: RequestInit = {}
): Promise<Response> {
  const url = `${getApiBase()}${path}`;
  const headers = new Headers(init.headers);
  headers.set('X-User-Id', userId);
  headers.set('X-Api-Key', getApiKey());

  return fetch(url, { ...init, headers });
}

/**
 * Gated proxy that checks authentication before forwarding.
 * Returns 401 immediately if the user is not authenticated, without
 * ever hitting the backend.
 *
 * @param path   - Backend path including leading slash
 * @param userId - Clerk userId, or null/undefined if unauthenticated
 * @param init   - Optional RequestInit
 * @returns Backend response or 401 JSON response
 */
export async function authenticatedProxy(
  path: string,
  userId: string | null | undefined,
  init: RequestInit = {}
): Promise<Response> {
  if (!userId) {
    return new Response(JSON.stringify({ detail: 'Not authenticated' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  return proxyToBackend(path, userId, init);
}
