import { useState } from 'react';
import { C } from '../theme';

export default function PairingScreen() {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [relationship, setRelationship] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const bind = async () => {
    const pairingCode = code.replace(/\D/g, '');
    if (pairingCode.length !== 6) {
      setError('请输入患者端显示的 6 位配对码');
      return;
    }
    if (!name.trim()) {
      setError('请输入患者看到的家属称呼');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const r = await fetch('/api/hospice/pairing/bind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: pairingCode,
          family_name: name.trim(),
          relationship: relationship.trim(),
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '绑定失败');
      localStorage.setItem('hospice_device_id', j.binding.device_id);
      localStorage.setItem('hospice_family_id', j.binding.family_id);
      localStorage.setItem('hospice_sender_name', j.binding.family_name);
      window.location.reload();
    } catch (e) {
      setError(e.message || '绑定失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ width: 420, maxWidth: '100%', border: `1px solid ${C.mist}33`, borderRadius: 8, background: C.card, padding: 22, boxShadow: '0 12px 38px rgba(30,24,16,.12)' }}>
        <div style={{ fontSize: 24, color: C.ink, fontFamily: 'Noto Serif SC,serif', marginBottom: 6 }}>绑定患者</div>
        <div style={{ fontSize: 13, color: C.inkFaint, lineHeight: 1.7, marginBottom: 18 }}>请在患者端设置里生成配对码，然后在这里输入。</div>
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder="6 位配对码"
          inputMode="numeric"
          style={inputStyle}
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="家属称呼，例如：女儿小雨"
          style={inputStyle}
        />
        <input
          value={relationship}
          onChange={(e) => setRelationship(e.target.value)}
          placeholder="关系，可选"
          style={inputStyle}
        />
        {error && <div style={{ color: C.red, fontSize: 13, marginBottom: 12 }}>{error}</div>}
        <button onClick={bind} disabled={busy} style={{ width: '100%', height: 42, border: 'none', borderRadius: 8, background: busy ? `${C.mist}66` : C.sage, color: 'white', fontSize: 15, cursor: busy ? 'not-allowed' : 'pointer' }}>
          {busy ? '绑定中...' : '完成绑定'}
        </button>
      </div>
    </div>
  );
}

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  border: `1px solid ${C.mist}33`,
  borderRadius: 8,
  padding: '12px 13px',
  marginBottom: 12,
  color: C.ink,
  fontSize: 15,
  outline: 'none',
  background: 'rgba(255,255,255,.76)',
};
