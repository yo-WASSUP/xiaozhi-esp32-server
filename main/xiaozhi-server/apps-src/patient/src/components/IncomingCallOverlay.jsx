import { useEffect, useState } from 'react';
import { C } from '../theme';

export default function IncomingCallOverlay({ caller, callType, onAccept, onDecline }) {
  const [tick, setTick] = useState(0);
  useEffect(() => { const id = setInterval(() => setTick(t => t + 1), 600); return () => clearInterval(id); }, []);

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 100, background: 'rgba(10,8,6,.78)', backdropFilter: 'blur(18px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 32, animation: 'fadeIn .4s ease' }}>
      <div style={{ position: 'relative', width: 200, height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ position: 'absolute', inset: -(i * 28), borderRadius: '50%', border: `1.5px solid ${C.sage}${['55', '33', '1a'][i]}`, animation: `ripple ${1.8 + i * .4}s ease-out ${i * .4}s infinite` }} />
        ))}
        <div style={{ width: 120, height: 120, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${C.sage}cc,#3a7055bb)`, boxShadow: `0 0 40px ${C.sage}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 48 }}>
          {caller.avatar}
        </div>
      </div>

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 36, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: 'rgba(255,255,255,.92)', letterSpacing: '.1em', marginBottom: 8 }}>
          {caller.from}
        </div>
        <div style={{ fontSize: 18, color: 'rgba(255,255,255,.5)', fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.12em' }}>
          {callType === 'video' ? '📹 视频通话邀请' : '📞 语音通话邀请'}
          {' · '}{'·'.repeat((tick % 3) + 1)}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 48 }}>
        <button onClick={onDecline} style={{ width: 88, height: 88, borderRadius: '50%', background: `${C.red}cc`, border: 'none', cursor: 'pointer', fontSize: 32, boxShadow: `0 4px 24px ${C.red}55`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
        <button onClick={onAccept} style={{ width: 88, height: 88, borderRadius: '50%', background: `${C.sage}cc`, border: 'none', cursor: 'pointer', fontSize: 32, boxShadow: `0 4px 24px ${C.sage}55`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✓</button>
      </div>
      <div style={{ fontSize: 14, color: 'rgba(255,255,255,.3)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>拒绝 · · · · · · 接听</div>
    </div>
  );
}
