import { C } from '../theme';
import { InkMountains, InkReeds } from '../components/InkArt';
import RobotAvatar from '../components/RobotAvatar';
import WaveBars from '../components/WaveBars';

const STATUS_MAP = {
  idle:      { label: '小暖随时在',         dot: C.sage,  anim: false },
  listening: { label: '小暖在聆听你说话…',   dot: C.amber, anim: true  },
  thinking:  { label: '小暖想一想…',         dot: C.mist,  anim: true  },
  speaking:  { label: '小暖正在说话',         dot: C.amber, anim: false },
};

const STAGE_LABELS = {
  rapport: '建立关系',
  life_review: '人生回顾',
  values: '价值提炼',
  relationships: '重要关系',
  legacy_message: '留言祝福',
  summary_confirm: '总结确认',
};

const STRATEGY_LABELS = {
  continue_deeper: '继续追问',
  comfort: '安抚',
  pause: '暂停',
  switch_topic: '转话题',
  ask_photo_context: '照片线索',
  output_rewrite: '安全改写',
  handoff_nurse: '人工介入',
  simple_followup: '轻量追问',
  summarize_confirm: '总结确认',
};

function formatLatency(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

export default function ChatScreen({ aiState, msg, lastHeard, connected, recording, userSpeaking, dignityMode, dignityStatus }) {
  const displayState = aiState === 'thinking' ? 'speaking' : (aiState === 'idle' && connected && recording && userSpeaking ? 'listening' : aiState);
  const { label, dot, anim } = STATUS_MAP[displayState] || STATUS_MAP.idle;
  const stage = STAGE_LABELS[dignityStatus?.current_stage] || dignityStatus?.current_stage || '建立关系';
  const strategy = STRATEGY_LABELS[dignityStatus?.strategy] || dignityStatus?.strategy || '继续追问';
  const responseLatency = formatLatency(dignityStatus?.client_response_latency_ms ?? dignityStatus?.response_latency_ms);

  return (
    <div style={{ position: 'relative', height: '100%', overflow: 'hidden' }}>
      <InkMountains />
      <InkReeds />

      {/* 顶部状态 */}
      <div style={{ position: 'absolute', top: 28, left: 0, right: 0, display: 'flex', justifyContent: 'center', zIndex: 5 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'center', padding: '0 32px' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: dot, boxShadow: `0 0 8px ${dot}`, animation: anim ? 'dotPulse 1.1s ease-in-out infinite' : 'none' }} />
          <span style={{ fontSize: 14, color: dot, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.08em', transition: 'color .6s' }}>{label}</span>
          {dignityMode && (
            <span style={{ fontSize: 12, color: dignityStatus?.strategy === 'handoff_nurse' ? C.red : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.04em' }}>
              尊严疗法 · {stage} · {strategy}
            </span>
          )}
          {dignityMode && responseLatency && (
            <span style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.04em' }}>
              回复耗时 {responseLatency}
            </span>
          )}
        </div>
      </div>

      {/* 主区：Orb + 文本 */}
      <div style={{ position: 'absolute', top: 72, bottom: 96, left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 28, zIndex: 5, padding: '0 42px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18 }}>
          <RobotAvatar state={displayState} />
          <div style={{ fontSize: 12, color: C.inkFaint, letterSpacing: '.18em', fontFamily: 'Noto Sans SC', fontWeight: 300, minHeight: 18, transition: 'opacity .4s' }}>
            {displayState === 'idle' && '· · ·'}
            {displayState === 'listening' && '正在聆听'}
            {displayState === 'thinking' && '稍等哦…'}
            {displayState === 'speaking' && '回应中'}
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
              {dignityMode ? <>我们慢慢聊，<br />从重要的回忆开始</> : <>我一直在呢，<br />您直接说话就好</>}
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
