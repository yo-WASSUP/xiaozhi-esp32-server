import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID, SENDER_NAME } from '../constants';
import { fmtTime } from '../utils/time';
import Bubble from '../components/Bubble';

export default function MessageScreen() {
  const [text, setText] = useState('');
  const [recording, setRec] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const [sent, setSent] = useState([]);
  const [flash, setFlash] = useState('');
  const [busy, setBusy] = useState(false);
  const [maxUploadMb, setMaxUploadMb] = useState(50);

  const recRef = useRef(null);
  const mediaRecRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);
  const videoInputRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    fetch('/api/hospice/config')
      .then(r => r.json())
      .then(j => { if (j && j.upload_max_mb) setMaxUploadMb(j.upload_max_mb); })
      .catch(() => {});
  }, []);

  const loadMessages = async () => {
    try {
      // 只拉当前家属与患者之间的这条会话线（contact_name = 自己的名字）
      const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(SENDER_NAME)}&limit=100`);
      const list = await r.json();
      setSent(list.slice().reverse().map(m => ({
        id: m.id,
        from: m.sender_role === 'patient' ? '父亲' : (m.sender_name || '你'),
        role: m.sender_role || 'family',
        type: m.message_type,
        content: m.content,
        filePath: m.file_path,
        dur: m.duration_ms ? `0:${String(Math.round(m.duration_ms / 1000)).padStart(2, '0')}` : null,
        time: fmtTime(m.created_at),
        played: !!m.played,
      })));
    } catch (e) { console.error('加载消息失败', e); }
  };

  useEffect(() => {
    loadMessages();
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    es.addEventListener('message.new', () => loadMessages());
    es.addEventListener('message.read', () => loadMessages());
    es.onerror = () => { };
    return () => es.close();
  }, []);

  // 新消息滚到底
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [sent.length]);

  const toast = (s) => { setFlash(s); setTimeout(() => setFlash(''), 2000); };

  const uploadFile = async (blob, filename) => {
    const fd = new FormData();
    fd.append('file', blob, filename);
    const r = await fetch('/api/hospice/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (!j.success) throw new Error(j.error || '上传失败');
    return j;
  };

  const postMessage = async (body) => {
    const r = await fetch('/api/hospice/message', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.error || '发送失败');
    return j;
  };

  const sendText = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      await postMessage({ device_id: DEVICE_ID, sender_role: 'family', sender_name: SENDER_NAME, type: 'text', content: text });
      setText('');
      loadMessages();
    } catch (e) { toast('⚠ ' + e.message); }
    finally { setBusy(false); }
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
      recRef.current = setInterval(() => setRecSecs(s => s + 1), 1000);
    } catch (e) {
      console.error(e);
      toast('⚠ 无法使用麦克风：' + e.message);
      setRec(false);
    }
  };

  const stopRecAndSend = async () => {
    clearInterval(recRef.current);
    const mr = mediaRecRef.current;
    const secs = recSecs;
    setRec(false);
    if (!mr) return;
    const stopped = new Promise(res => { mr.onstop = res; });
    mr.stop();
    await stopped;
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (secs < 1) { toast('录音太短'); return; }

    setBusy(true);
    try {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' });
      const ext = (mr.mimeType || '').includes('ogg') ? '.ogg' : (mr.mimeType || '').includes('mp4') ? '.m4a' : '.webm';
      const up = await uploadFile(blob, `voice-${Date.now()}${ext}`);
      await postMessage({
        device_id: DEVICE_ID, sender_role: 'family', sender_name: SENDER_NAME,
        type: 'voice', content: `语音 ${secs}s`, file_path: up.url, duration_ms: secs * 1000,
      });
      setRecSecs(0);
      loadMessages();
    } catch (e) { console.error(e); toast('⚠ ' + e.message); }
    finally { setBusy(false); }
  };

  const cancelRec = () => {
    clearInterval(recRef.current);
    const mr = mediaRecRef.current;
    if (mr && mr.state !== 'inactive') { mr.onstop = null; mr.stop(); }
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    chunksRef.current = [];
    setRec(false); setRecSecs(0);
  };

  const onPickPhoto = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setBusy(true);
    try {
      const up = await uploadFile(file, file.name);
      await postMessage({
        device_id: DEVICE_ID, sender_role: 'family', sender_name: SENDER_NAME,
        type: 'photo', content: file.name, file_path: up.url,
      });
      loadMessages();
    } catch (err) { console.error(err); toast('⚠ ' + err.message); }
    finally { setBusy(false); }
  };

  const onPickVideo = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > maxUploadMb * 1024 * 1024) {
      toast(`⚠ 视频过大（${(file.size / 1024 / 1024).toFixed(1)}MB），最多 ${maxUploadMb}MB`);
      return;
    }
    setBusy(true);
    try {
      const up = await uploadFile(file, file.name);
      await postMessage({
        device_id: DEVICE_ID, sender_role: 'family', sender_name: SENDER_NAME,
        type: 'video', content: file.name, file_path: up.url,
      });
      loadMessages();
    } catch (err) { console.error(err); toast('⚠ ' + err.message); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, display: 'flex', flexDirection: 'column', animation: 'fadeUp .4s ease' }}>
      {/* 顶部标题 */}
      <div style={{ padding: '44px 20px 12px', borderBottom: `0.5px solid ${C.mist}22` }}>
        <div style={{ fontSize: 20, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em' }}>和父亲的对话</div>
        <div style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginTop: 2 }}>消息会在小暖陪伴时播报给父亲</div>
      </div>

      {/* 聊天流 */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 14px 14px', background: `linear-gradient(180deg,transparent,${C.mist}08)` }}>
        {sent.length === 0 && <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, textAlign: 'center', padding: '40px 0', opacity: .5 }}>还没有消息，说句话试试</div>}
        {sent.map(m => <Bubble key={m.id} m={m} isMine={m.role !== 'patient'} />)}
      </div>

      {/* Flash */}
      {flash && <div style={{ position: 'absolute', bottom: 150, left: '50%', transform: 'translateX(-50%)', background: flash.startsWith('⚠') ? C.red : C.sage, borderRadius: 14, padding: '8px 16px', fontSize: 13, color: 'white', fontFamily: 'Noto Sans SC', fontWeight: 300, zIndex: 10, animation: 'fadeIn .3s ease' }}>{flash}</div>}

      {/* 录音浮层 */}
      {recording && (
        <div style={{ position: 'absolute', bottom: 80, left: 0, right: 0, background: 'rgba(30,24,16,.92)', padding: '20px 16px', display: 'flex', alignItems: 'center', gap: 14, zIndex: 20 }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: C.red, animation: 'pulse 1s ease-in-out infinite' }} />
            <span style={{ color: 'white', fontFamily: 'Noto Sans SC', fontSize: 14 }}>录音中 {String(Math.floor(recSecs / 60)).padStart(2, '0')}:{String(recSecs % 60).padStart(2, '0')}</span>
          </div>
          <button onClick={cancelRec} style={{ padding: '8px 14px', borderRadius: 12, border: `1px solid ${C.mist}66`, background: 'transparent', color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>取消</button>
          <button onClick={stopRecAndSend} style={{ padding: '8px 16px', borderRadius: 12, border: 'none', background: C.amber, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>发送</button>
        </div>
      )}

      {/* 底部输入栏 */}
      <div style={{ borderTop: `0.5px solid ${C.mist}22`, background: C.card, padding: '8px 10px', display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <button onClick={() => fileInputRef.current && fileInputRef.current.click()} disabled={busy || recording} title="照片"
          style={{ width: 40, height: 40, borderRadius: '50%', border: `1px solid ${C.mist}33`, background: 'transparent', cursor: busy || recording ? 'not-allowed' : 'pointer', fontSize: 18, flexShrink: 0, opacity: busy || recording ? .4 : 1 }}>📷</button>
        <button onClick={() => videoInputRef.current && videoInputRef.current.click()} disabled={busy || recording} title={`视频（最大 ${maxUploadMb}MB）`}
          style={{ width: 40, height: 40, borderRadius: '50%', border: `1px solid ${C.mist}33`, background: 'transparent', cursor: busy || recording ? 'not-allowed' : 'pointer', fontSize: 18, flexShrink: 0, opacity: busy || recording ? .4 : 1 }}>🎬</button>
        <button onClick={startRec} disabled={busy || recording} title="语音"
          style={{ width: 40, height: 40, borderRadius: '50%', border: `1px solid ${C.mist}33`, background: recording ? C.red + '33' : 'transparent', cursor: busy || recording ? 'not-allowed' : 'pointer', fontSize: 18, flexShrink: 0, opacity: busy ? .4 : 1 }}>🎤</button>
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="说点什么…" rows={1}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); } }}
          style={{ flex: 1, minHeight: 40, maxHeight: 100, padding: '10px 12px', borderRadius: 18, border: `1px solid ${C.mist}33`, background: 'white', resize: 'none', fontSize: 15, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 300, outline: 'none', lineHeight: 1.4 }} />
        <button onClick={sendText} disabled={!text.trim() || busy}
          style={{ padding: '10px 14px', borderRadius: 18, border: 'none', background: text.trim() && !busy ? C.amber : `${C.mist}44`, color: 'white', fontSize: 13, fontFamily: 'Noto Sans SC', fontWeight: 400, cursor: text.trim() && !busy ? 'pointer' : 'not-allowed', flexShrink: 0 }}>发送</button>
        <input ref={fileInputRef} type="file" accept="image/*" onChange={onPickPhoto} style={{ display: 'none' }} />
        <input ref={videoInputRef} type="file" accept="video/*" onChange={onPickVideo} style={{ display: 'none' }} />
      </div>
    </div>
  );
}
