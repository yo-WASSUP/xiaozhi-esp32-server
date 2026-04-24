import { useEffect, useState } from 'react';
import { C } from '../theme';

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const gr = now.getHours() < 6 ? '凌晨' : now.getHours() < 12 ? '上午' : now.getHours() < 18 ? '下午' : '晚上';
  return (
    <div style={{ textAlign: 'right', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
      <div style={{ fontSize: 28, color: C.ink, letterSpacing: '.12em' }}>{hh}:{mm}</div>
      <div style={{ fontSize: 11, color: C.inkFaint, letterSpacing: '.1em' }}>{gr}好</div>
    </div>
  );
}

export default function TopBar({ screen, setScreen, unread }) {
  const navBtn = (id, icon, label) => (
    <button onClick={() => setScreen(id)} style={{
      display: 'flex', alignItems: 'center', gap: 6, padding: '8px 16px', borderRadius: 20, border: 'none', cursor: 'pointer',
      background: screen === id ? `${C.mist}22` : 'transparent',
      transition: 'background .2s', position: 'relative',
    }}>
      <span style={{ fontSize: 20 }}>{icon}</span>
      <span style={{ fontSize: 14, color: screen === id ? C.ink : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.06em' }}>{label}</span>
      {id === 'inbox' && unread > 0 && (
        <div style={{ position: 'absolute', top: 4, right: 8, width: 16, height: 16, borderRadius: '50%', background: C.amber, fontSize: 10, color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Noto Sans SC' }}>
          {unread}
        </div>
      )}
    </button>
  );

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 72, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 48px', borderBottom: `0.5px solid ${C.mist}22`, backdropFilter: 'blur(12px)', background: `rgba(243,233,212,0.55)` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${C.amber}ee,#b87340cc)`, boxShadow: `0 0 16px ${C.amber}44` }} />
        <div>
          <div style={{ fontSize: 18, fontWeight: 400, color: C.ink, letterSpacing: '.14em', fontFamily: 'Noto Serif SC, serif' }}>小暖</div>
          <div style={{ fontSize: 11, color: C.inkFaint, letterSpacing: '.08em', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>安宁疗护陪伴助手</div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        {navBtn('chat', '💬', '陪伴对话')}
        {navBtn('inbox', '💌', '家人消息')}
      </div>
      <Clock />
    </div>
  );
}
