import { useEffect, useRef, useState } from 'react';
import {
  Microphone,
  Paperclip,
  PaperPlaneRight,
  WarningCircle,
  X,
} from '@phosphor-icons/react';
import { C } from '../theme';
import { DEVICE_ID, FAMILY_ID, SENDER_NAME } from '../constants';
import { fmtTime } from '../utils/time';
import Bubble from '../components/Bubble';

export default function MessageScreen() {
  const [text, setText] = useState('');
  const [recording, setRec] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const [sent, setSent] = useState([]);
  const [flash, setFlash] = useState(null);
  const [busy, setBusy] = useState(false);
  const [maxUploadMb, setMaxUploadMb] = useState(50);

  const recRef = useRef(null);
  const mediaRecRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const mediaInputRef = useRef(null);
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
      const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&family_id=${encodeURIComponent(FAMILY_ID)}&limit=100`);
      const list = await r.json();
      setSent(list.slice().reverse().map(m => ({
        id: m.id,
        from: m.sender_role === 'patient' ? '家人' : (m.sender_name || '你'),
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

  const toast = (text, tone = 'error') => {
    setFlash({ text, tone });
    setTimeout(() => setFlash(null), 2400);
  };

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
      await postMessage({ device_id: DEVICE_ID, family_id: FAMILY_ID, sender_role: 'family', sender_name: SENDER_NAME, type: 'text', content: text });
      setText('');
      loadMessages();
    } catch (e) { toast(e.message); }
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
      toast('无法使用麦克风：' + e.message);
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
    if (secs < 1) { toast('录音太短，请重新录制'); return; }

    setBusy(true);
    try {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' });
      const ext = (mr.mimeType || '').includes('ogg') ? '.ogg' : (mr.mimeType || '').includes('mp4') ? '.m4a' : '.webm';
      const up = await uploadFile(blob, `voice-${Date.now()}${ext}`);
      await postMessage({
        device_id: DEVICE_ID, family_id: FAMILY_ID, sender_role: 'family', sender_name: SENDER_NAME,
        type: 'voice', content: `语音 ${secs}s`, file_path: up.url, duration_ms: secs * 1000,
      });
      setRecSecs(0);
      loadMessages();
    } catch (e) { console.error(e); toast(e.message); }
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

  const onPickMedia = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    if (!isImage && !isVideo) {
      toast('请选择照片或视频');
      return;
    }
    if (isVideo && file.size > maxUploadMb * 1024 * 1024) {
      toast(`视频过大（${(file.size / 1024 / 1024).toFixed(1)}MB），最多 ${maxUploadMb}MB`);
      return;
    }
    setBusy(true);
    try {
      const up = await uploadFile(file, file.name);
      await postMessage({
        device_id: DEVICE_ID, family_id: FAMILY_ID, sender_role: 'family', sender_name: SENDER_NAME,
        type: isVideo ? 'video' : 'photo', content: file.name, file_path: up.url,
      });
      loadMessages();
    } catch (err) { console.error(err); toast(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="screen" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* 顶部标题 */}
      <div className="screen-header" style={{ borderBottom: `1px solid ${C.outline}`, background: 'rgba(244,247,245,.92)' }}>
        <div className="screen-title">和家人的对话</div>
        <div className="screen-subtitle">消息会在小暖陪伴时播报给家人</div>
      </div>

      {/* 聊天流 */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '14px 14px 18px' }}>
        {sent.length === 0 && <div style={{ fontSize: 13, color: C.inkFaint, fontWeight: 500, textAlign: 'center', padding: '44px 0' }}>还没有消息，先向家人问个好吧</div>}
        {sent.map(m => <Bubble key={m.id} m={m} isMine={m.role !== 'patient'} />)}
      </div>

      {/* Flash */}
      {flash && (
        <div role="alert" style={{ position: 'absolute', bottom: 84, left: 16, right: 16, background: flash.tone === 'error' ? C.red : C.sage, borderRadius: 14, padding: '11px 14px', fontSize: 13, color: 'white', fontWeight: 500, zIndex: 10, animation: 'fadeIn .2s ease', display: 'flex', alignItems: 'center', gap: 8, boxShadow: '0 8px 24px rgba(23,33,28,.18)' }}>
          <WarningCircle size={19} weight="fill" />
          <span>{flash.text}</span>
        </div>
      )}

      {/* 录音浮层 */}
      {recording && (
        <div style={{ position: 'absolute', bottom: 80, left: 0, right: 0, background: 'rgba(30,24,16,.92)', padding: '20px 16px', display: 'flex', alignItems: 'center', gap: 14, zIndex: 20 }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Microphone size={20} color={C.red} weight="fill" />
            <span style={{ color: 'white', fontFamily: 'Noto Sans SC', fontSize: 14 }}>录音中 {String(Math.floor(recSecs / 60)).padStart(2, '0')}:{String(recSecs % 60).padStart(2, '0')}</span>
          </div>
          <button type="button" onClick={cancelRec} aria-label="取消录音" style={{ width: 44, height: 44, borderRadius: 14, border: `1px solid ${C.mist}66`, background: 'transparent', color: 'white', cursor: 'pointer', display: 'grid', placeItems: 'center' }}><X size={20} /></button>
          <button type="button" onClick={stopRecAndSend} style={{ height: 44, padding: '0 18px', borderRadius: 14, border: 'none', background: C.amber, color: 'white', fontSize: 13, fontWeight: 650, cursor: 'pointer' }}>发送</button>
        </div>
      )}

      {/* 底部输入栏 */}
      <div style={{ borderTop: `1px solid ${C.outline}`, background: '#f9fbfa', padding: '10px 10px calc(10px + env(safe-area-inset-bottom))', display: 'flex', alignItems: 'flex-end', gap: 8 }}>
        <button type="button" className="icon-button" onClick={() => mediaInputRef.current && mediaInputRef.current.click()} disabled={busy || recording} aria-label={`发送照片或视频，视频最大 ${maxUploadMb}MB`}
          style={{ cursor: busy || recording ? 'not-allowed' : 'pointer', opacity: busy || recording ? .4 : 1 }}><Paperclip size={21} /></button>
        <button type="button" className="icon-button" onClick={startRec} disabled={busy || recording} aria-label="录制语音"
          style={{ cursor: busy || recording ? 'not-allowed' : 'pointer', opacity: busy ? .4 : 1 }}><Microphone size={21} /></button>
        <textarea value={text} onChange={e => setText(e.target.value)} placeholder="说点什么…" rows={1}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(); } }}
          style={{ flex: 1, minHeight: 48, maxHeight: 112, padding: '12px 14px', borderRadius: 16, border: `1px solid ${C.outline}`, background: 'white', resize: 'none', fontSize: 15, color: C.ink, fontWeight: 400, outline: 'none', lineHeight: 1.5 }} />
        <button type="button" onClick={sendText} disabled={!text.trim() || busy} aria-label="发送消息"
          style={{ width: 48, height: 48, borderRadius: 16, border: 'none', background: text.trim() && !busy ? C.amber : C.surfaceVariant, color: text.trim() && !busy ? C.onPrimary : C.inkFaint, cursor: text.trim() && !busy ? 'pointer' : 'not-allowed', flexShrink: 0, display: 'grid', placeItems: 'center' }}><PaperPlaneRight size={21} weight="fill" /></button>
        <input ref={mediaInputRef} type="file" accept="image/*,video/*" onChange={onPickMedia} style={{ display: 'none' }} />
      </div>
    </div>
  );
}
