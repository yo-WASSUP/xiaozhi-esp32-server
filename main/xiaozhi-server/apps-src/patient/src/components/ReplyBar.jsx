import { useRef, useState } from 'react';
import { C } from '../theme';

/** 回复输入区：文本 / 录音 / 媒体 */
export default function ReplyBar({ onSendText, onSendVoice, onPickMedia, disabled, maxUploadMb }) {
  const [text, setText] = useState('');
  const [rec, setRec] = useState(false);
  const [recSecs, setRecSecs] = useState(0);

  const mediaRecRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const recTimerRef = useRef(null);
  const mediaInputRef = useRef(null);

  const submitText = () => {
    const t = text.trim();
    if (!t) return;
    onSendText(t);
    setText('');
  };

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
      const mime = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      mediaRecRef.current = mr;
      mr.ondataavailable = e => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
      mr.start();
      setRec(true); setRecSecs(0);
      recTimerRef.current = setInterval(() => setRecSecs(s => s + 1), 1000);
    } catch (e) {
      console.error(e);
      alert('无法使用麦克风：' + e.message);
      setRec(false);
    }
  };

  const stopRec = async () => {
    clearInterval(recTimerRef.current);
    const mr = mediaRecRef.current;
    const secs = recSecs;
    setRec(false); setRecSecs(0);
    if (!mr) return;
    const stopped = new Promise(res => { mr.onstop = res; });
    mr.stop();
    await stopped;
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (secs < 1) return;
    const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' });
    const ext = (mr.mimeType || '').includes('ogg') ? '.ogg' : (mr.mimeType || '').includes('mp4') ? '.m4a' : '.webm';
    onSendVoice(blob, ext, secs);
  };

  const handleMediaPick = (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const isVideo = file.type.startsWith('video/');
    const isImage = file.type.startsWith('image/');
    if (!isVideo && !isImage) {
      alert('请选择照片或视频');
      return;
    }
    if (isVideo && file.size > maxUploadMb * 1024 * 1024) {
      alert(`视频过大（${(file.size / 1024 / 1024).toFixed(1)}MB），最多 ${maxUploadMb}MB`);
      return;
    }
    onPickMedia && onPickMedia(file);
  };

  return (
    <div style={{ borderTop: `0.5px solid ${C.mist}33`, padding: '14px 20px', background: 'rgba(255,250,242,0.6)', display: 'flex', alignItems: 'center', gap: 10 }}>
      <button onClick={rec ? stopRec : startRec} disabled={disabled}
        style={{
          width: 44, height: 44, borderRadius: '50%', border: 'none',
          cursor: disabled ? 'not-allowed' : 'pointer',
          background: rec ? C.red : `${C.amber}22`,
          color: rec ? 'white' : C.amber,
          fontSize: 20, flexShrink: 0,
          boxShadow: rec ? `0 0 0 4px ${C.red}33` : 'none',
          transition: 'all .2s',
        }}>
        {rec ? `${recSecs}s` : '🎤'}
      </button>

      <button onClick={() => mediaInputRef.current && mediaInputRef.current.click()}
        disabled={disabled || rec}
        title={`照片或视频（视频最大 ${maxUploadMb}MB）`}
        style={{
          width: 44, height: 44, borderRadius: '50%', border: 'none',
          cursor: (disabled || rec) ? 'not-allowed' : 'pointer',
          background: `${C.sage}22`, color: C.sage,
          fontSize: 20, flexShrink: 0, opacity: (disabled || rec) ? .4 : 1,
        }}>📎</button>
      <input ref={mediaInputRef} type="file" accept="image/*,video/*" onChange={handleMediaPick} style={{ display: 'none' }} />

      <input value={text} onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submitText(); }}
        placeholder={rec ? '录音中…' : '写点什么回给家人…'}
        disabled={rec || disabled}
        style={{
          flex: 1, padding: '12px 16px', borderRadius: 22,
          border: `1px solid ${C.mist}33`, background: 'white',
          fontSize: 16, fontFamily: 'Noto Serif SC,serif', fontWeight: 300,
          color: C.ink, outline: 'none',
        }} />

      <button onClick={submitText} disabled={!text.trim() || disabled}
        style={{
          padding: '10px 20px', borderRadius: 22, border: 'none',
          background: text.trim() ? C.amber : `${C.mist}33`,
          color: text.trim() ? 'white' : C.inkFaint,
          fontSize: 14, fontFamily: 'Noto Sans SC', fontWeight: 400,
          cursor: text.trim() ? 'pointer' : 'not-allowed', flexShrink: 0,
        }}>发送</button>
    </div>
  );
}
