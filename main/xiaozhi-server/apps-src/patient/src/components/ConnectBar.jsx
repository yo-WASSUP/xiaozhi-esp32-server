import { useState } from 'react';
import { C } from '../theme';

/** 开发调试栏：连接小暖服务器、文字输入、切换录音。生产阶段可以隐藏。 */
export default function ConnectBar({ connected, onConnect, onDisconnect, onSendText, recording, onToggleRec, micOk }) {
  const [text, setText] = useState('');
  return (
    <div style={{ position: 'absolute', bottom: 86, right: 24, zIndex: 30, display: 'flex', gap: 10, alignItems: 'center', background: 'rgba(255,250,242,0.92)', backdropFilter: 'blur(12px)', padding: '10px 14px', borderRadius: 18, border: '1px solid rgba(143,163,176,0.22)', boxShadow: '0 4px 18px rgba(0,0,0,0.08)', flexWrap: 'wrap', maxWidth: '72vw' }}>
      {!connected ? (
        <button onClick={onConnect} style={{ padding: '6px 16px', borderRadius: 14, border: 'none', background: C.sage, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>
          连接服务器
        </button>
      ) : (
        <>
          <span style={{ fontSize: 12, color: C.sage, fontFamily: 'Noto Sans SC' }}>● 已连接</span>
          <button onClick={onToggleRec} disabled={!micOk}
            style={{
              padding: '6px 12px', borderRadius: 14,
              border: `1px solid ${recording ? C.red : C.amber}66`,
              background: recording ? `${C.red}22` : `${C.amber}18`,
              color: recording ? C.red : C.amber,
              fontSize: 13, fontFamily: 'Noto Sans SC',
              cursor: micOk ? 'pointer' : 'not-allowed', opacity: micOk ? 1 : 0.4,
            }}>
            {recording ? '⏹ 停止说话' : '🎤 开始说话'}
          </button>
          <input value={text} onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && text.trim()) { onSendText(text); setText(''); } }}
            placeholder="输入文字测试…"
            style={{ padding: '6px 10px', borderRadius: 12, border: `1px solid ${C.mist}44`, fontSize: 13, fontFamily: 'Noto Sans SC', outline: 'none', width: 180 }} />
          <button onClick={() => { if (text.trim()) { onSendText(text); setText(''); } }}
            style={{ padding: '6px 12px', borderRadius: 14, border: 'none', background: C.amber, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>
            发送
          </button>
          <button onClick={onDisconnect}
            style={{ padding: '6px 10px', borderRadius: 14, border: `1px solid ${C.inkFaint}44`, background: 'transparent', color: C.inkFaint, fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>
            断开
          </button>
        </>
      )}
    </div>
  );
}
