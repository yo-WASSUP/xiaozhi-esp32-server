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

export default function TopBar({ connected, recording, unread, micOk, connectStatus, onOpenSettings }) {
  const statusColor = connected && recording ? C.sage : connected ? C.amber : C.red;
  const statusText = connected && recording
    ? '小暖在线聆听'
    : connected
      ? '小暖在线'
      : '正在连接小暖';

  return (
    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 72, zIndex: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 48px', borderBottom: `0.5px solid ${C.mist}22`, backdropFilter: 'blur(12px)', background: `rgba(243,233,212,0.55)` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${C.amber}ee,#b87340cc)`, boxShadow: `0 0 16px ${C.amber}44` }} />
        <div>
          <div style={{ fontSize: 18, fontWeight: 400, color: C.ink, letterSpacing: '.14em', fontFamily: 'Noto Serif SC, serif' }}>小暖</div>
          <div style={{ fontSize: 11, color: C.inkFaint, letterSpacing: '.08em', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>安宁疗护陪伴助手</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 22, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: statusColor, fontSize: 14, letterSpacing: '.08em' }}>
          <span style={{ width: 9, height: 9, borderRadius: '50%', background: statusColor, boxShadow: `0 0 8px ${statusColor}`, animation: recording ? 'dotPulse 1.2s ease-in-out infinite' : 'none' }} />
          {statusText}
        </div>
        <div style={{ color: unread > 0 ? C.amber : C.inkFaint, fontSize: 14, letterSpacing: '.08em' }}>
          家人消息 {unread > 0 ? `${unread} 条未读` : '无未读'}
        </div>
        {!micOk && (
          <div style={{ color: C.red, fontSize: 13, letterSpacing: '.06em' }}>需要麦克风权限</div>
        )}
        {connectStatus && connected && (
          <div style={{ color: C.inkFaint, fontSize: 12, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{connectStatus}</div>
        )}
        <button
          onClick={onOpenSettings}
          title="设置"
          style={{
            width: 38,
            height: 38,
            borderRadius: '50%',
            border: `1px solid ${C.mist}44`,
            background: 'rgba(255,250,242,.72)',
            color: C.inkMid,
            cursor: 'pointer',
            fontSize: 18,
            lineHeight: 1,
          }}
        >
          ⚙
        </button>
      </div>
      <Clock />
    </div>
  );
}
