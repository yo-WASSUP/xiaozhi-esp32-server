import { C } from '../theme';

/** 自动在线失败时的兜底连接条。 */
export default function ConnectBar({ connected, onConnect, recording, micOk, connectStatus }) {
  return (
    <div style={{ position: 'absolute', bottom: 24, left: 28, zIndex: 30, display: 'flex', gap: 12, alignItems: 'center', background: 'rgba(255,250,242,0.94)', backdropFilter: 'blur(12px)', padding: '12px 16px', borderRadius: 18, border: '1px solid rgba(143,163,176,0.22)', boxShadow: '0 4px 18px rgba(0,0,0,0.08)', maxWidth: 520 }}>
      <div style={{ fontSize: 13, color: connected && recording ? C.sage : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, lineHeight: 1.5 }}>
        {connected && recording ? '安安正在听您说话' : connectStatus || (micOk ? '正在恢复安安连接' : '需要允许麦克风权限')}
      </div>
      {(!connected || !recording || !micOk) && (
        <button onClick={onConnect} style={{ padding: '8px 16px', borderRadius: 14, border: 'none', background: C.sage, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer', flexShrink: 0 }}>
          重新连接
        </button>
      )}
    </div>
  );
}
