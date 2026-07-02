let _getToken: () => string | null = () => null;
let _refresh: () => Promise<string | null> = async () => null;
let _logout: () => void = () => {};

/** Called once by AuthProvider to wire up token access */
export function configureApiClient(
  getToken: () => string | null,
  refresh: () => Promise<string | null>,
  logout: () => void,
) {
  _getToken = getToken;
  _refresh = refresh;
  _logout = logout;
}

const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = _getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });

  // On 401, attempt exactly one token refresh then retry
  if (res.status === 401) {
    const newToken = await _refresh();
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`);
      res = await fetch(`${BASE}${path}`, {
        ...init,
        headers,
        credentials: 'include',
      });
    } else {
      _logout();
    }
  }

  return res;
}
