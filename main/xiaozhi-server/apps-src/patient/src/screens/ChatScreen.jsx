import { C } from '../theme';
import { InkMountains, InkReeds } from '../components/InkArt';
import Orb from '../components/Orb';
import WaveBars from '../components/WaveBars';

const STATUS_MAP = {
  idle:      { label: '小暖随时在',         dot: C.sage,  anim: false },
  listening: { label: '小暖在聆听你说话…',   dot: C.amber, anim: true  },
  thinking:  { label: '小暖想一想…',         dot: C.mist,  anim: true  },
  speaking:  { label: '小暖正在说话',         dot: C.amber, anim: false },
};

export default function ChatScreen({ aiState, msg, lastHeard, connected, recording }) {
  const { label, dot, anim } = STATUS_MAP[aiState] || STATUS_MAP.idle;

  return (
    <div style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
      <InkMountains />
      <InkReeds />

      {/* 顶部状态 */}
      <div style={{ position: 'absolute', top: 28, left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: dot, boxShadow: `0 0 8px ${dot}`, animation: anim ? 'dotPulse 1.1s ease-in-out infinite' : 'none' }} />
          <span style={{ fontSize: 14, color: dot, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.08em', transition: 'color .6s' }}>{label}</span>
        </div>
      </div>

      {/* 主区：Orb + 文本 */}
      <div style={{ position: 'absolute', top: 72, bottom: 96, left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 28, zIndex: 5, padding: '0 42px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
          <Orb state={aiState} />
          <div style={{ fontSize: 12, color: C.inkFaint, letterSpacing: '.18em', fontFamily: 'Noto Sans SC', fontWeight: 300, minHeight: 18, transition: 'opacity .4s' }}>
            {aiState === 'idle' && '· · ·'}
            {aiState === 'listening' && '正在聆听'}
            {aiState === 'thinking' && '稍等哦…'}
            {aiState === 'speaking' && '说话中'}
          </div>
        </div>
        <div style={{ width: '100%', maxWidth: 440, textAlign: 'center' }}>
          {msg ? (
            <div key={msg} style={{ animation: 'fadeUp .9s ease' }}>
              <div style={{ fontSize: 28, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: C.ink, lineHeight: 1.75, letterSpacing: '.04em', textWrap: 'pretty', marginBottom: 14 }}>
                「{msg}」
              </div>
              <div style={{ display: 'inline-block', fontSize: 13, color: C.inkFaint, letterSpacing: '.1em', fontFamily: 'Noto Sans SC', fontWeight: 300, borderLeft: `2.5px solid ${C.amber}77`, paddingLeft: 12 }}>
                小暖说
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 24, color: 'rgba(30,24,16,.24)', fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em', lineHeight: 2.1 }}>
              我一直在呢，<br />您直接说话就好
            </div>
          )}
        </div>
      </div>

      {/* 底部波形 */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, minHeight: 96, zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '12px 36px', borderTop: `0.5px solid ${C.mist}22`, backdropFilter: 'blur(16px)', background: 'rgba(243,233,212,.38)' }}>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <WaveBars state={aiState} />
        </div>
        <div style={{ minHeight: 18, maxWidth: 420, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontSize: 12, fontWeight: 300, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {!connected ? '正在保持连接' : recording ? (lastHeard ? `刚听到：${lastHeard}` : '小暖正在听') : '小暖在线，稍后恢复聆听'}
        </div>
      </div>
    </div>
  );
}
