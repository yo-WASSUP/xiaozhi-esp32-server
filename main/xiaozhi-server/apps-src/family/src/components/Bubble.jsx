import { useRef, useState } from 'react';
import {
  Camera,
  Check,
  Circle,
  Heart,
  Microphone,
  Pause,
  Play,
  User,
  VideoCamera,
} from '@phosphor-icons/react';
import { C } from '../theme';

/** 单条消息气泡（右=自己/家属，左=家人/患者） */
export default function Bubble({ m, isMine }) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);

  const togglePlay = () => {
    const a = audioRef.current; if (!a) return;
    if (a.paused) { a.play(); setPlaying(true); } else { a.pause(); setPlaying(false); }
  };

  const bubbleBg = isMine ? C.primaryContainer : '#ffffff';
  const bubbleBorder = isMine ? `1px solid ${C.amber}35` : `1px solid ${C.outline}`;

  return (
    <div style={{ display: 'flex', flexDirection: isMine ? 'row-reverse' : 'row', alignItems: 'flex-start', gap: 8, margin: '10px 0' }}>
      <div style={{ width: 36, height: 36, borderRadius: 14, background: isMine ? C.primaryContainer : C.surfaceVariant, color: isMine ? C.amber : C.inkMid, border: `1px solid ${C.outline}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {isMine ? <User size={20} weight="duotone" /> : <Heart size={20} weight="duotone" />}
      </div>
      <div style={{ maxWidth: '70%', display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start' }}>
        <div style={{ fontSize: 10, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginBottom: 2, padding: '0 4px' }}>
          {m.from}，{m.time}
        </div>

        {m.type === 'text' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 16, padding: '11px 14px', fontSize: 15, fontWeight: 400, color: C.ink, lineHeight: 1.55, wordBreak: 'break-word' }}>
            {m.content}
          </div>
        )}

        {m.type === 'voice' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 16, padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10, minWidth: 150 }}>
            <button type="button" aria-label={playing ? '暂停语音' : '播放语音'} onClick={togglePlay} style={{ width: 36, height: 36, borderRadius: 12, background: playing ? C.amber : `${C.amber}20`, color: playing ? C.onPrimary : C.amber, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {playing ? <Pause size={18} weight="fill" /> : <Play size={18} weight="fill" />}
            </button>
            <Microphone size={17} color={C.inkMid} />
            <span style={{ fontSize: 13, color: C.ink, fontWeight: 500 }}>{m.dur || ''}</span>
            {m.filePath && <audio ref={audioRef} src={m.filePath} onEnded={() => setPlaying(false)} preload="none" />}
          </div>
        )}

        {m.type === 'photo' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: 4, overflow: 'hidden', maxWidth: 220 }}>
            {m.filePath
              ? <img src={m.filePath} alt="" style={{ display: 'block', width: '100%', borderRadius: 10, maxHeight: 260, objectFit: 'cover' }} />
              : <div style={{ padding: '10px 14px', fontSize: 13, color: C.inkFaint, display: 'flex', alignItems: 'center', gap: 7 }}><Camera size={18} />{m.content || '照片'}</div>}
          </div>
        )}

        {m.type === 'video' && (
          <div style={{ background: bubbleBg, border: bubbleBorder, borderRadius: 14, padding: 4, overflow: 'hidden', maxWidth: 240 }}>
            {m.filePath
              ? <video src={m.filePath} controls preload="metadata" style={{ display: 'block', width: '100%', borderRadius: 10, maxHeight: 320, background: '#000' }} />
              : <div style={{ padding: '10px 14px', fontSize: 13, color: C.inkFaint, display: 'flex', alignItems: 'center', gap: 7 }}><VideoCamera size={18} />{m.content || '视频'}</div>}
          </div>
        )}

        {isMine && (
          <div style={{ fontSize: 10, color: m.played ? C.sage : C.mist, fontWeight: 500, marginTop: 4, padding: '0 4px', display: 'flex', alignItems: 'center', gap: 3 }}>
            {m.played ? <Check size={12} weight="bold" /> : <Circle size={7} weight="fill" />}
            {m.played ? '已读' : '未读'}
          </div>
        )}
      </div>
    </div>
  );
}
