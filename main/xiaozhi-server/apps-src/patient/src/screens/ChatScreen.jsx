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

export default function ChatScreen({ aiState, msg }) {
  const { label, dot, anim } = STATUS_MAP[aiState] || STATUS_MAP.idle;

  return (
    <>
      <InkMountains />
      <InkReeds />

      {/* 顶部状态 */}
      <div style={{ position: 'absolute', top: 90, left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: dot, boxShadow: `0 0 8px ${dot}`, animation: anim ? 'dotPulse 1.1s ease-in-out infinite' : 'none' }} />
          <span style={{ fontSize: 14, color: dot, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.08em', transition: 'color .6s' }}>{label}</span>
        </div>
      </div>

      {/* 主区：Orb + 文本 */}
      <div style={{ position: 'absolute', top: 72, bottom: 72, left: 0, right: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 64, zIndex: 5 }}>
        <div style={{ width: '20%' }} />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
          <Orb state={aiState} />
          <div style={{ fontSize: 12, color: C.inkFaint, letterSpacing: '.18em', fontFamily: 'Noto Sans SC', fontWeight: 300, minHeight: 18, transition: 'opacity .4s' }}>
            {aiState === 'idle' && '· · ·'}
            {aiState === 'listening' && '正在聆听'}
            {aiState === 'thinking' && '稍等哦…'}
            {aiState === 'speaking' && '说话中'}
          </div>
        </div>
        <div style={{ width: '26%', paddingRight: 48 }}>
          {msg ? (
            <div key={msg} style={{ animation: 'fadeUp .9s ease' }}>
              <div style={{ fontSize: 30, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: C.ink, lineHeight: 1.85, letterSpacing: '.04em', textWrap: 'pretty', marginBottom: 18 }}>
                「{msg}」
              </div>
              <div style={{ fontSize: 13, color: C.inkFaint, letterSpacing: '.1em', fontFamily: 'Noto Sans SC', fontWeight: 300, borderLeft: `2.5px solid ${C.amber}77`, paddingLeft: 12 }}>
                小暖说
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 20, color: 'rgba(30,24,16,.2)', fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em', lineHeight: 2.1 }}>
              我在呢，<br />有什么<br />想说的嘛~
            </div>
          )}
        </div>
      </div>

      {/* 底部波形 */}
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 72, zIndex: 10, display: 'flex', alignItems: 'center', padding: '0 48px', borderTop: `0.5px solid ${C.mist}22`, backdropFilter: 'blur(16px)', background: 'rgba(243,233,212,.38)' }}>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'center' }}>
          <WaveBars state={aiState} />
        </div>
      </div>
    </>
  );
}
