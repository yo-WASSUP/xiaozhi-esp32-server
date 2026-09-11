import { C } from '../theme';

/** 语音服务确实不可用时显示的恢复提示。 */
export default function ConnectBar({ connected, onConnect, micOk, connectStatus }) {
  const canReconnect = !connected || !micOk || Boolean(connectStatus);

  return (
    <div style={{ position: 'absolute', bottom: 28, left: '50%', transform: 'translateX(-50%)', zIndex: 30, display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'center', background: 'rgba(255,250,242,0.96)', backdropFilter: 'blur(12px)', padding: '12px 16px', borderRadius: 18, border: '1px solid rgba(143,163,176,0.22)', boxShadow: '0 4px 18px rgba(0,0,0,0.08)', width: 'max-content', maxWidth: 'calc(100% - 40px)' }}>
      <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 400, lineHeight: 1.5 }}>
        {connectStatus || (micOk ? '语音助手暂时无法使用' : '请允许使用麦克风')}
      </div>
      {canReconnect && (
        <button onClick={onConnect} style={{ padding: '8px 16px', borderRadius: 14, border: 'none', background: C.sage, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer', flexShrink: 0 }}>
          重试
        </button>
      )}
    </div>
  );
}
