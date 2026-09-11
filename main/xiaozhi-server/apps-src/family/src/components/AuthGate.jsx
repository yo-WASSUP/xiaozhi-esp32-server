import { cloneElement, useEffect, useState } from 'react';

function scopeMultipartRequests(patientId) {
  if (!patientId || window.__hospiceFetchScoped) return;
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    if (init.body instanceof FormData && typeof input === 'string' && input.startsWith('/api/hospice/')) {
      const url = new URL(input, window.location.origin);
      if (!url.searchParams.has('device_id')) url.searchParams.set('device_id', patientId);
      input = `${url.pathname}${url.search}`;
    }
    return originalFetch(input, init);
  };
  window.__hospiceFetchScoped = true;
}

function syncFamily(user) {
  const patientId = user?.patient_ids?.[0] || '';
  if (patientId) localStorage.setItem('family_hospice_device_id', patientId);
  localStorage.setItem('family_hospice_sender_name', user.display_name || user.username);
}

export default function AuthGate({ children }) {
  const [state, setState] = useState({ loading: true, enabled: true, user: null, error: '' });
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const status = await fetch('/api/auth/status').then((response) => response.json());
        if (!status.enabled) {
          setState({ loading: false, enabled: false, user: null, error: '' });
          return;
        }
        let response = await fetch('/api/auth/me');
        if (response.status === 401) {
          await fetch('/api/auth/refresh', { method: 'POST' });
          response = await fetch('/api/auth/me');
        }
        if (!response.ok) {
          setState({ loading: false, enabled: true, user: null, error: '' });
          return;
        }
        const payload = await response.json();
        if (payload.user?.role !== 'family') throw new Error('请使用家属账号登录家属端');
        syncFamily(payload.user);
        scopeMultipartRequests(payload.user.patient_ids?.[0]);
        setState({ loading: false, enabled: true, user: payload.user, error: '' });
      } catch (error) {
        setState({ loading: false, enabled: true, user: null, error: error.message || '登录状态检查失败' });
      }
    })();
  }, []);

  useEffect(() => {
    if (!state.user) return;
    const checkSession = async () => {
      if (document.visibilityState === 'hidden') return;
      try {
        const response = await fetch('/api/auth/me');
        const payload = await response.json();
        if (!response.ok || payload.user?.role !== 'family' || payload.user?.username !== state.user.username) {
          setState((current) => ({ ...current, user: null, error: '当前账号登录状态已变化，请重新登录。' }));
        }
      } catch { /* Keep the current screen during a temporary network outage. */ }
    };
    window.addEventListener('focus', checkSession);
    document.addEventListener('visibilitychange', checkSession);
    return () => {
      window.removeEventListener('focus', checkSession);
      document.removeEventListener('visibilitychange', checkSession);
    };
  }, [state.user]);

  const login = async (event) => {
    event.preventDefault();
    setBusy(true);
    setState((current) => ({ ...current, error: '' }));
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '登录失败');
      if (payload.user?.role !== 'family') {
        await fetch('/api/auth/logout', { method: 'POST' });
        throw new Error('请使用家属账号登录家属端');
      }
      syncFamily(payload.user);
      window.location.reload();
    } catch (error) {
      setState((current) => ({ ...current, error: error.message || '登录失败' }));
      setBusy(false);
    }
  };

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    localStorage.removeItem('family_hospice_device_id');
    localStorage.removeItem('family_hospice_family_id');
    localStorage.removeItem('family_hospice_sender_name');
    window.location.reload();
  };

  if (state.loading) return <div className="auth-page"><div className="auth-card">正在检查登录状态…</div></div>;
  if (!state.enabled) return children;
  if (state.user) return cloneElement(children, { onLogout: logout });
  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={login}>
        <div className="auth-brand">安安</div>
        <h1>家属端登录</h1>
        <p>请输入管理员分配的账号和密码。</p>
        <label htmlFor="auth-username">账号</label>
        <input id="auth-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label htmlFor="auth-password">密码</label>
        <div className="password-field">
          <input id="auth-password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <button className="password-toggle" type="button" aria-controls="auth-password" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? '隐藏' : '显示'}</button>
        </div>
        {state.error && <div className="auth-error" role="alert">{state.error}</div>}
        <button type="submit" disabled={busy}>{busy ? '正在登录…' : '登录'}</button>
      </form>
    </main>
  );
}
