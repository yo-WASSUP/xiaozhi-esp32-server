import { useRef, useState } from 'react';
import { C } from '../theme';

/** 收件箱里的气泡（大号；右=我/患者，左=家人） */
export default function ChatBubble({ m, isMine }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);

  const bubbleBg = isMine ? `${C.sage}22` : 'rgba(255,250,242,0.92)';
  const bubbleBorder = isMine ? `1px solid ${C.sage}44` : `1px solid ${C.mist}33`;

  const togglePlay = () => {
    const a = audioRef.current; if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); }
    else { a.pause(); setPlaying(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: isMine ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 12, margin: '14px 0' }}>
      <div style={{ width: 48, height: 48, borderRadius: '50%', background: `${C.amber}22`, border: `1.5px solid ${C.amber}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, flexShrink: 0 }}>
        {m.avatar}
      </div>
      <div style={{ maxWidth: '62%', display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start' }}>
        <div style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginBottom: 4, padding: '0 4px' }}>
          {m.from} · {m.time}
        </div>
        {m.type === 'text' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 18, padding: '14px 20px', fontSize: 22, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: C.ink, lineHeight: 1.7, letterSpacing: '.03em', wordBreak: 'break-word' }}>
            {m.content}
          </div>
        )}
        {m.type === 'voice' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 18, padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 14, minWidth: 200 }}>
            <button onClick={togglePlay} style={{ width: 44, height: 44, borderRadius: '50%', background: playing ? C.amber : `${C.amber}33`, border: 'none', cursor: 'pointer', fontSize: 20, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {playing ? '⏸' : '▶️'}
            </button>
            <div style={{ flex: 1, fontSize: 16, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>语音 {m.dur || ''}</div>
            {m.filePath && <audio ref={audioRef} src={m.filePath} onEnded={() => setPlaying(false)} preload="none" />}
          </div>
        )}
        {m.type === 'photo' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 18, padding: 6, overflow: 'hidden', maxWidth: 260 }}>
            {m.filePath
              ? <img src={m.filePath} alt="" style={{ display: 'block', width: '100%', borderRadius: 14, maxHeight: 320, objectFit: 'cover' }} />
              : <div style={{ padding: '24px 28px', fontSize: 16, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>📷 {m.content || '照片'}</div>}
          </div>
        )}
        {m.type === 'video' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 18, padding: 6, overflow: 'hidden', maxWidth: 320 }}>
            {m.filePath
              ? <video src={m.filePath} controls preload="metadata" style={{ display: 'block', width: '100%', borderRadius: 14, maxHeight: 380, background: '#000' }} />
              : <div style={{ padding: '24px 28px', fontSize: 16, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>🎬 {m.content || '视频'}</div>}
          </div>
        )}
      </div>
    </div>
  );
}
