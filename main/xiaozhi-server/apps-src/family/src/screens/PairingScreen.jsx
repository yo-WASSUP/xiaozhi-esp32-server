import { useState } from 'react';
import { DeviceMobile, LinkSimple, ShieldCheck } from '@phosphor-icons/react';
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
    <div style={{ position: 'absolute', inset: 0, overflowY: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'calc(24px + env(safe-area-inset-top)) 20px calc(24px + env(safe-area-inset-bottom))' }}>
      <div style={{ width: 420, maxWidth: '100%', border: `1px solid ${C.outline}`, borderRadius: 20, background: C.card, padding: 22, boxShadow: '0 18px 48px rgba(47,107,85,.10)' }}>
        <div style={{ width: 52, height: 52, borderRadius: 16, background: C.primaryContainer, color: C.amber, display: 'grid', placeItems: 'center', marginBottom: 18 }}><DeviceMobile size={27} weight="duotone" /></div>
        <div style={{ fontSize: 25, color: C.ink, fontWeight: 650, letterSpacing: '-.02em', marginBottom: 7 }}>连接家人的设备</div>
        <div style={{ fontSize: 14, color: C.inkFaint, lineHeight: 1.65, marginBottom: 22 }}>在患者端生成 6 位配对码，然后填写您的称呼即可完成连接。</div>
        <label style={labelStyle} htmlFor="pairing-code">配对码</label>
        <input
          id="pairing-code"
          value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          placeholder="请输入 6 位数字"
          inputMode="numeric"
          style={inputStyle}
        />
        <label style={labelStyle} htmlFor="family-name">您的称呼</label>
        <input
          id="family-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="例如：女儿小雨"
          style={inputStyle}
        />
        <label style={labelStyle} htmlFor="relationship">与家人的关系 <span style={{ color: C.inkFaint, fontWeight: 400 }}>选填</span></label>
        <input
          id="relationship"
          value={relationship}
          onChange={(e) => setRelationship(e.target.value)}
          placeholder="例如：女儿"
          style={inputStyle}
        />
        {error && <div role="alert" style={{ color: C.red, background: `${C.red}10`, borderRadius: 12, padding: '10px 12px', fontSize: 13, marginBottom: 14 }}>{error}</div>}
        <button type="button" className="tap-button" onClick={bind} disabled={busy} style={{ width: '100%', border: 'none', borderRadius: 16, background: busy ? C.surfaceVariant : C.sage, color: busy ? C.inkFaint : 'white', fontSize: 15, fontWeight: 650, cursor: busy ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
          {busy ? <LinkSimple size={20} /> : <ShieldCheck size={20} weight="fill" />}
          {busy ? '正在连接' : '安全连接'}
        </button>
      </div>
    </div>
  );
}

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  height: 50,
  border: `1px solid ${C.outline}`,
  borderRadius: 14,
  padding: '0 14px',
  marginBottom: 16,
  color: C.ink,
  fontSize: 15,
  outline: 'none',
  background: '#fff',
};

const labelStyle = {
  display: 'block',
  color: C.inkMid,
  fontSize: 13,
  fontWeight: 600,
  marginBottom: 7,
};
