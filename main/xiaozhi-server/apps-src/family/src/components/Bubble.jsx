import { useRef, useState } from 'react';
import { C } from '../theme';

/** 单条消息气泡（右=自己/家属，左=家人/患者） */
export default function Bubble({ m, isMine }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);

  const togglePlay = () => {
    const a = audioRef.current; if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); } else { a.pause(); setPlaying(false); }
  };

  const bubbleBg = isMine ? `${C.amber}22` : 'rgba(255,250,242,0.95)';
  const bubbleBorder = isMine ? `1px solid ${C.amber}55` : `1px solid ${C.mist}33`;

  return (
    <div style={{ display: 'flex', flexDirection: isMine ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 8, margin: '10px 0' }}>
      <div style={{ width: 34, height: 34, borderRadius: '50%', background: `${C.amber}22`, border: `1px solid ${C.amber}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>
        {isMine ? '👤' : '🧑‍🦳'}
      </div>
      <div style={{ maxWidth: '70%', display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start' }}>
        <div style={{ fontSize: 10, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginBottom: 2, padding: '0 4px' }}>
          {m.from} · {m.time}
        </div>

        {m.type === 'text' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: '10px 14px', fontSize: 15, fontFamily: 'Noto Sans SC', fontWeight: 300, color: C.ink, lineHeight: 1.55, wordBreak: 'break-word' }}>
            {m.content}
          </div>
        )}

        {m.type === 'voice' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10, minWidth: 140 }}>
            <button onClick={togglePlay} style={{ width: 32, height: 32, borderRadius: '50%', background: playing ? C.amber : `${C.amber}33`, border: 'none', cursor: 'pointer', fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {playing ? '⏸' : '▶️'}
            </button>
            <span style={{ fontSize: 13, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>🎤 {m.dur || ''}</span>
            {m.filePath && <audio ref={audioRef} src={m.filePath} onEnded={() => setPlaying(false)} preload="none" />}
          </div>
        )}

        {m.type === 'photo' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: 4, overflow: 'hidden', maxWidth: 220 }}>
            {m.filePath
              ? <img src={m.filePath} alt="" style={{ display: 'block', width: '100%', borderRadius: 10, maxHeight: 260, objectFit: 'cover' }} />
              : <div style={{ padding: '10px 14px', fontSize: 13, color: C.inkFaint }}>📷 {m.content || '照片'}</div>}
          </div>
        )}

        {m.type === 'video' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: 4, overflow: 'hidden', maxWidth: 240 }}>
            {m.filePath
              ? <video src={m.filePath} controls preload="metadata" style={{ display: 'block', width: '100%', borderRadius: 10, maxHeight: 320, background: '#000' }} />
              : <div style={{ padding: '10px 14px', fontSize: 13, color: C.inkFaint }}>🎬 {m.content || '视频'}</div>}
          </div>
        )}

        {isMine && (
          <div style={{ fontSize: 10, color: m.played ? C.sage : C.mist, fontFamily: 'Noto Sans SC', fontWeight: 300, marginTop: 3, padding: '0 4px' }}>
            {m.played ? '✓ 已读' : '• 未读'}
          </div>
        )}
      </div>
    </div>
  );
}
