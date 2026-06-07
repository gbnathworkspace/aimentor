import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { proxyToBackend, authenticatedProxy } from '../lib/api-proxy';

// ---------------------------------------------------------------------------
// Environment setup
// ---------------------------------------------------------------------------

const MOCK_API_BASE = 'http://localhost:8000';
const MOCK_API_KEY = 'test-secret-key';

beforeEach(() => {
  vi.stubEnv('MENTORMAN_API_BASE', MOCK_API_BASE);
  vi.stubEnv('MENTORMAN_API_KEY', MOCK_API_KEY);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

// ---------------------------------------------------------------------------
// proxyToBackend
// ---------------------------------------------------------------------------

describe('proxyToBackend', () => {
  it('forwards request to backend with X-User-Id and X-Api-Key headers', async () => {
    const mockResponse = new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse);

    const result = await proxyToBackend('/api/profile', 'user_123');

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe(`${MOCK_API_BASE}/api/profile`);

    const headers = options?.headers as Headers;
    expect(headers.get('X-User-Id')).toBe('user_123');
    expect(headers.get('X-Api-Key')).toBe(MOCK_API_KEY);
    expect(result.status).toBe(200);
  });

  it('passes through method and body from init', async () => {
    const mockResponse = new Response('{}', { status: 201 });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse);

    const body = JSON.stringify({ goal: 'Learn React' });
    await proxyToBackend('/api/profile', 'user_456', {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/json' },
    });

    const [, options] = fetchSpy.mock.calls[0];
    expect(options?.method).toBe('POST');
    expect(options?.body).toBe(body);

    const headers = options?.headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.get('X-User-Id')).toBe('user_456');
    expect(headers.get('X-Api-Key')).toBe(MOCK_API_KEY);
  });

  it('preserves existing headers while adding auth headers', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));

    await proxyToBackend('/api/skills', 'user_789', {
      headers: { 'Accept': 'application/json', 'X-Custom': 'value' },
    });

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    const headers = options?.headers as Headers;
    expect(headers.get('Accept')).toBe('application/json');
    expect(headers.get('X-Custom')).toBe('value');
    expect(headers.get('X-User-Id')).toBe('user_789');
    expect(headers.get('X-Api-Key')).toBe(MOCK_API_KEY);
  });
});

// ---------------------------------------------------------------------------
// authenticatedProxy
// ---------------------------------------------------------------------------

describe('authenticatedProxy', () => {
  it('returns 401 when userId is null', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    const result = await authenticatedProxy('/api/profile', null);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.status).toBe(401);
    const body = await result.json();
    expect(body.detail).toBe('Not authenticated');
  });

  it('returns 401 when userId is undefined', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    const result = await authenticatedProxy('/api/profile', undefined);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.status).toBe(401);
    const body = await result.json();
    expect(body.detail).toBe('Not authenticated');
  });

  it('returns 401 when userId is empty string', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    const result = await authenticatedProxy('/api/profile', '');

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.status).toBe(401);
  });

  it('proxies to backend when userId is present', async () => {
    const mockResponse = new Response(JSON.stringify({ goal: 'Learn' }), { status: 200 });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockResponse);

    const result = await authenticatedProxy('/api/profile', 'user_abc');

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(result.status).toBe(200);

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe(`${MOCK_API_BASE}/api/profile`);
    const headers = options?.headers as Headers;
    expect(headers.get('X-User-Id')).toBe('user_abc');
    expect(headers.get('X-Api-Key')).toBe(MOCK_API_KEY);
  });

  it('forwards init options when authenticated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 200 }));

    await authenticatedProxy('/api/profile', 'user_xyz', {
      method: 'DELETE',
    });

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(options?.method).toBe('DELETE');
  });
});
