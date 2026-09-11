// Cookies remain HttpOnly; only the application role is sent by JavaScript.
export function installSession(role) {
  const originalFetch = window.fetch.bind(window);
  let refreshPending;
  const scopedFetch = (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) return originalFetch(input, init);
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    headers.set('X-Hospice-Role', role);
    return originalFetch(input, { ...init, headers });
  };
  const refresh = () => {
    if (!refreshPending) {
      refreshPending = scopedFetch('/api/auth/refresh', { method: 'POST' })
        .finally(() => { refreshPending = undefined; });
    }
    return refreshPending;
  };
  window.fetch = async (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (url.origin === window.location.origin && url.pathname === '/api/auth/refresh') {
      return (await refresh()).clone();
    }
    const response = await scopedFetch(input, init);
    if (response.status !== 401 || url.origin !== window.location.origin ||
        !url.pathname.startsWith('/api/') || ['/api/auth/login', '/api/auth/logout', '/api/auth/status'].includes(url.pathname)) return response;
    // Middleware rejects unauthenticated requests before running the handler.
    if ((await refresh()).ok) return scopedFetch(input, init);
    return response;
  };
}
