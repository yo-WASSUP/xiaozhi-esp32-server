import { installSession } from '../../shared/session';
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import InterviewAudioEditor from './components/InterviewAudioEditor';
import LegacyVideoReview from './components/LegacyVideoReview';

installSession(window.location.pathname.startsWith('/admin/') ? 'admin' : 'clinician');

const adminPage = window.location.pathname.startsWith('/admin/');
document.title = adminPage ? '安安 · 管理端' : '安安 · 医护端';

function Login({ onLogin, error, busy, role }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  return (
    <main className="center-page">
      <form className="card login-card" onSubmit={(event) => {
        event.preventDefault();
        onLogin(username.trim(), password);
      }}>
        <div className="brand">安安</div>
        <h1>{role === 'admin' ? '管理员登录' : '医护端登录'}</h1>
        <p>{role === 'admin' ? '使用配置文件中的管理员账号登录。' : '使用管理员分配的医护账号登录。'}</p>
        <label htmlFor="username">账号</label>
        <input id="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
        <label htmlFor="password">密码</label>
        <div className="password-field">
          <input id="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          <button className="password-toggle" type="button" aria-controls="password" aria-label={showPassword ? '隐藏密码' : '显示密码'} aria-pressed={showPassword} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? '隐藏' : '显示'}</button>
        </div>
        {error && <div className="error" role="alert">{error}</div>}
        <button disabled={busy}>{busy ? '正在登录…' : '登录'}</button>
      </form>
    </main>
  );
}

function AccountManager({ user, onLogout }) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ username: '', display_name: '', password: '', role: 'patient', patient_ids: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadUsers = async () => {
    const response = await fetch('/api/admin/users');
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || '账号列表加载失败');
    setUsers(payload.users || []);
  };

  useEffect(() => { loadUsers().catch((reason) => setError(reason.message)); }, []);

  const saveUsers = (payload) => setUsers(payload.users || []);
  const createUser = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          patient_ids: form.patient_ids.split(/[,，\s]+/).filter(Boolean),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '创建账号失败');
      saveUsers(payload);
      setForm({ username: '', display_name: '', password: '', role: 'patient', patient_ids: '' });
    } catch (reason) {
      setError(reason.message || '创建账号失败');
    } finally {
      setBusy(false);
    }
  };

  const updateUser = async (account, changes) => {
    setError('');
    try {
      const response = await fetch(`/api/admin/users/${encodeURIComponent(account.username)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '账号修改失败');
      saveUsers(payload);
    } catch (reason) {
      setError(reason.message || '账号修改失败');
    }
  };

  const resetPassword = (account) => {
    const password = window.prompt(`为 ${account.username} 设置新密码（至少 8 个字符）`);
    if (password !== null) updateUser(account, { password });
  };

  const editPatients = (account) => {
    const value = window.prompt('填写可访问的患者设备 ID，多个用逗号分隔', (account.patient_ids || []).join(', '));
    if (value !== null) updateUser(account, { patient_ids: value.split(/[,，\s]+/).filter(Boolean) });
  };

  return <main className="dashboard">
    <header>
      <div><div className="brand">安安管理端</div><h1>账号管理</h1></div>
      <div className="account"><span>{user.display_name}</span><button className="secondary" onClick={onLogout}>退出登录</button></div>
    </header>
    <form className="card create-form" onSubmit={createUser}>
      <h2>创建账号</h2>
      <div className="form-grid">
        <label>账号<input value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} required /></label>
        <label>姓名<input value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} required /></label>
        <label>初始密码<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength="8" required /></label>
        <label>角色<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}><option value="patient">患者</option><option value="family">家属</option><option value="clinician">医护</option></select></label>
        <label className="wide">患者设备 ID<input value={form.patient_ids} onChange={(event) => setForm({ ...form, patient_ids: event.target.value })} placeholder="患者账号必填；多个设备 ID 用逗号分隔" required={form.role === 'patient'} /></label>
      </div>
      <button disabled={busy}>{busy ? '正在创建…' : '创建账号'}</button>
    </form>
    {error && <div className="error">{error}</div>}
    <section className="card user-list">
      <h2>已有账号</h2>
      {users.length === 0 ? <div className="empty">还没有普通账号。</div> : users.map((account) => <article className="user-row" key={account.username}>
        <div><strong>{account.display_name}</strong><span>{account.username} · {account.role}</span><small>{account.patient_ids?.join('、') || '未关联患者'}</small></div>
        <div className="actions"><button className="secondary" onClick={() => editPatients(account)}>患者权限</button><button className="secondary" onClick={() => resetPassword(account)}>重置密码</button><button className={account.enabled ? 'danger' : 'success'} onClick={() => updateUser(account, { enabled: !account.enabled })}>{account.enabled ? '停用' : '启用'}</button></div>
      </article>)}
    </section>
  </main>;
}

function Dashboard({ user, onLogout }) {
  const [patientId, setPatientId] = useState(user.patient_ids?.[0] || '');
  const [alerts, setAlerts] = useState([]);
  const [taskBusy, setTaskBusy] = useState('');
  const [dignityTab, setDignityTab] = useState('audio');
  const [interviewSegments, setInterviewSegments] = useState([]);
  const [interviewBusy, setInterviewBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!patientId) return;
    setError('');
    Promise.all([
      fetch(`/api/hospice/safety-alerts?device_id=${encodeURIComponent(patientId)}`).then((response) => response.json()),
      fetch(`/api/hospice/interview/audio-segments/latest?device_id=${encodeURIComponent(patientId)}`).then((response) => response.json()),
    ]).then(([alertData, interviewData]) => {
      setAlerts(alertData.alerts || []);
      setInterviewSegments(interviewData.segments || []);
    }).catch((reason) => setError(reason.message || '患者信息加载失败'));
  }, [patientId]);

  const toggleInterviewSegment = (segmentId) => {
    setInterviewSegments((items) => items.map((item) => (
      item.id === segmentId ? { ...item, deleted: !item.deleted } : item
    )));
  };

  const saveInterviewSegments = async (segments) => {
    setInterviewBusy(true);
    setError('');
    try {
      const response = await fetch('/api/hospice/interview/audio-segments/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: patientId, segments }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) throw new Error(payload.error || '访谈记录保存失败');
      setInterviewSegments(payload.segments || segments);
    } catch (reason) {
      setError(reason.message || '访谈记录保存失败');
    } finally {
      setInterviewBusy(false);
    }
  };

  const updateSafetyTask = async (alert, action) => {
    const note = window.prompt('填写处置备注（可以留空）', alert.disposition_note || '');
    if (note === null) return;
    setTaskBusy(alert.alert_id);
    try {
      const response = await fetch(`/api/hospice/safety-alerts/${encodeURIComponent(alert.alert_id)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: patientId,
          alert_id: alert.alert_id,
          task_action: action,
          note,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '处置失败');
      setAlerts(payload.alerts || []);
    } catch (reason) {
      setError(reason.message || '处置失败');
    } finally {
      setTaskBusy('');
    }
  };

  const openAlertCount = alerts.filter((alert) => !['released', 'closed'].includes(alert.task?.status)).length;

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <div>
          <div className="brand">安安医护端</div>
          <h1>患者工作台</h1>
          <p className="dashboard-kicker">审核访谈记录，处理安全预警，整理生命影像。</p>
        </div>
        <div className="account"><span>{user.display_name}</span><button className="secondary" onClick={onLogout}>退出登录</button></div>
      </header>
      <section className="patient-context">
        {user.patient_ids?.length ? (
          <div className="patient-picker">
            <span className="patient-picker__mark" aria-hidden="true">患</span>
            <label htmlFor="patient">
              <span>当前患者</span>
              <select id="patient" value={patientId} onChange={(event) => setPatientId(event.target.value)}>
                {user.patient_ids.map((id) => <option key={id} value={id}>{id}</option>)}
              </select>
            </label>
          </div>
        ) : <div className="empty">该账号尚未关联患者，请由管理员授权。</div>}
        {patientId && <div className="workload-summary" aria-label="当前患者工作概览">
          <div><strong>{openAlertCount}</strong><span>待处理预警</span></div>
          <div><strong>{interviewSegments.length}</strong><span>访谈片段</span></div>
          <div><strong>{user.patient_ids?.length || 0}</strong><span>关联患者</span></div>
        </div>}
      </section>
      {error && <div className="error">{error}</div>}
      {patientId && (alerts.length === 0 ? (
        <div className="safety-clear" role="status">
          <span aria-hidden="true">✓</span>
          <div><strong>当前无安全预警</strong><small>发现风险线索后会在这里生成医护处置任务。</small></div>
        </div>
      ) : <section className="card safety-section">
        <div className="section-heading">
          <div><div className="section-eyebrow">需要关注</div><h2>安全预警处置</h2></div>
          <span className="alert-count">{openAlertCount} 项待处理</span>
        </div>
        {alerts.map((alert) => {
          const status = alert.task?.status || 'pending';
          const resolved = ['released', 'closed'].includes(status);
          const busy = taskBusy === alert.alert_id;
          return <article className={`alert-card level-${alert.level || 'L1'}`} key={alert.alert_id}>
            <div className="alert-head"><strong>{alert.level} · {alert.category || '安全风险'}</strong><span>{status}</span></div>
            <p>患者原话：{alert.patient_text || alert.evidence || '未记录'}</p>
            <p>判定依据：{alert.reason || '需要医护人员复核'}</p>
            {alert.disposition_note && <p>处置备注：{alert.disposition_note}</p>}
            {!resolved && <div className="actions">
              {status === 'pending' && <button disabled={busy} onClick={() => updateSafetyTask(alert, 'acknowledge')}>确认接单</button>}
              {alert.level !== 'L3' && <button className="danger" disabled={busy} onClick={() => updateSafetyTask(alert, 'escalate')}>升级 L3</button>}
              <button className="success" disabled={busy} onClick={() => updateSafetyTask(alert, 'release')}>确认安全并解除暂停</button>
              <button className="secondary" disabled={busy} onClick={() => updateSafetyTask(alert, 'close')}>关闭任务</button>
            </div>}
          </article>;
        })}
      </section>)}
      {patientId && <section className="card dignity-review-section">
        <div className="section-heading">
          <div>
            <div className="section-eyebrow">尊严疗法</div>
            <h2>访谈与生命影像审核</h2>
          </div>
          <span className="section-meta">{patientId}</span>
        </div>
        <div className="review-tabs" role="tablist" aria-label="尊严疗法审核工具">
          <button
            type="button"
            role="tab"
            aria-selected={dignityTab === 'audio'}
            className={dignityTab === 'audio' ? 'active' : ''}
            onClick={() => setDignityTab('audio')}
          >
            访谈记录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={dignityTab === 'video'}
            className={dignityTab === 'video' ? 'active' : ''}
            onClick={() => setDignityTab('video')}
          >
            生命影像审核
          </button>
        </div>
        <div className="review-panel" role="tabpanel">
          {dignityTab === 'audio' ? (
            <InterviewAudioEditor
              segments={interviewSegments}
              busy={interviewBusy}
              onToggleSegment={toggleInterviewSegment}
              onSave={saveInterviewSegments}
            />
          ) : (
            <LegacyVideoReview key={patientId} deviceId={patientId} />
          )}
        </div>
      </section>}
    </main>
  );
}

function App() {
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [user, setUser] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadSession = async () => {
    const status = await fetch('/api/auth/status').then((response) => response.json());
    setEnabled(Boolean(status.enabled));
    if (!status.enabled) {
      setLoading(false);
      return;
    }
    let response = await fetch('/api/auth/me');
    if (response.status === 401) {
      await fetch('/api/auth/refresh', { method: 'POST' });
      response = await fetch('/api/auth/me');
    }
    if (response.ok) {
      const payload = await response.json();
      const expectedRole = adminPage ? 'admin' : 'clinician';
      if (payload.user?.role === expectedRole) setUser(payload.user);
      else setError(adminPage ? '请使用管理员账号登录管理端' : '请使用医护账号登录医护端');
    }
    setLoading(false);
  };

  useEffect(() => { loadSession().catch(() => setLoading(false)); }, []);

  const login = async (username, password) => {
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || '登录失败');
      const expectedRole = adminPage ? 'admin' : 'clinician';
      if (payload.user?.role !== expectedRole) {
        await fetch('/api/auth/logout', { method: 'POST' });
        throw new Error(adminPage ? '请使用管理员账号登录管理端' : '请使用医护账号登录医护端');
      }
      setUser(payload.user);
    } catch (reason) {
      setError(reason.message || '登录失败');
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    setUser(null);
  };

  if (loading) return <main className="center-page">正在检查登录状态…</main>;
  if (!enabled) return <main className="center-page"><div className="card">服务端尚未启用账号鉴权。</div></main>;
  if (user) return adminPage ? <AccountManager user={user} onLogout={logout} /> : <Dashboard user={user} onLogout={logout} />;
  return <Login onLogin={login} error={error} busy={busy} role={adminPage ? 'admin' : 'clinician'} />;
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>);
