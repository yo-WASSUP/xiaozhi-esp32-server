import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID, PATIENT_NAME } from '../constants';
import { fmtTime } from '../utils/time';
import { InkMountains } from '../components/InkArt';
import ContactItem from '../components/ContactItem';
import ChatBubble from '../components/ChatBubble';
import ReplyBar from '../components/ReplyBar';

export default function InboxScreen({ contacts, refreshContacts, eventTick, maxUploadMb }) {
  const [selected, setSelected] = useState(null);
  const [thread, setThread] = useState([]);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);

  // 默认选中第一个联系人
  useEffect(() => {
    if (!selected && contacts.length > 0) setSelected(contacts[0].contact_name);
    // eslint-disable-next-line
  }, [contacts.length]);

  const loadThread = async (name) => {
    if (!name) { setThread([]); return; }
    try {
      const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(name)}&limit=200`);
      const list = await r.json();
      setThread(list.slice().reverse().map(m => ({
        id: m.id,
        role: m.sender_role || 'family',
        from: m.sender_role === 'patient' ? '我' : (m.sender_name || '家人'),
        avatar: m.sender_role === 'patient' ? '🧑‍🦳' : '👤',
        type: m.message_type,
        content: m.content,
        filePath: m.file_path,
        dur: m.duration_ms ? `0:${String(Math.round(m.duration_ms / 1000)).padStart(2, '0')}` : null,
        time: fmtTime(m.created_at),
      })));
    } catch (e) { console.error('加载会话失败', e); }
  };

  const markThreadRead = async (name) => {
    try {
      await fetch(`/api/hospice/thread/read?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(name)}`, { method: 'POST' });
      refreshContacts && refreshContacts();
    } catch (e) { console.error('标记已读失败', e); }
  };

  // 切联系人 → 拉消息并清未读
  useEffect(() => {
    if (!selected) return;
    loadThread(selected).then(() => markThreadRead(selected));
    // eslint-disable-next-line
  }, [selected]);

  // 服务端事件触发重拉
  useEffect(() => {
    if (selected) loadThread(selected);
    // eslint-disable-next-line
  }, [eventTick]);

  // 新消息滚到底
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread.length]);

  const sendText = async (content) => {
    if (!selected) return;
    setBusy(true);
    try {
      await fetch('/api/hospice/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID, sender_role: 'patient', sender_name: PATIENT_NAME,
          contact_name: selected, type: 'text', content,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送失败：' + e.message); }
    finally { setBusy(false); }
  };

  const sendVoice = async (blob, ext, secs) => {
    if (!selected) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', blob, `voice-${Date.now()}${ext}`);
      const u = await fetch('/api/hospice/upload', { method: 'POST', body: fd });
      const uj = await u.json();
      if (!uj.success) throw new Error(uj.error || '上传失败');
      await fetch('/api/hospice/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID, sender_role: 'patient', sender_name: PATIENT_NAME,
          contact_name: selected, type: 'voice',
          content: `语音 ${secs}s`, file_path: uj.url, duration_ms: secs * 1000,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送语音失败：' + e.message); }
    finally { setBusy(false); }
  };

  const sendVideo = async (file) => {
    if (!selected) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file, file.name || `video-${Date.now()}.mp4`);
      const u = await fetch('/api/hospice/upload', { method: 'POST', body: fd });
      const uj = await u.json();
      if (!uj.success) throw new Error(uj.error || '上传失败');
      await fetch('/api/hospice/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID, sender_role: 'patient', sender_name: PATIENT_NAME,
          contact_name: selected, type: 'video',
          content: file.name || '视频', file_path: uj.url,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送视频失败：' + e.message); }
    finally { setBusy(false); }
  };

  const activeContact = contacts.find(c => c.contact_name === selected);

  return (
    <>
      <InkMountains />
      <div style={{ position: 'absolute', top: 72, bottom: 0, left: 0, right: 0, zIndex: 5, display: 'flex', animation: 'slideLeft .4s ease' }}>

        {/* 左：联系人列表 */}
        <div style={{ width: 320, flexShrink: 0, borderRight: `0.5px solid ${C.mist}33`, display: 'flex', flexDirection: 'column', background: 'rgba(255,250,242,0.4)' }}>
          <div style={{ padding: '20px 24px 12px', fontSize: 20, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: C.ink, letterSpacing: '.1em', borderBottom: `0.5px solid ${C.mist}22` }}>
            家人
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {contacts.length === 0 ? (
              <div style={{ textAlign: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, fontSize: 16, lineHeight: 2, opacity: .5, marginTop: 60, padding: '0 20px' }}>
                还没有家人的消息<br />等家人发来问候
              </div>
            ) : contacts.map(c => (
              <ContactItem key={c.contact_name} c={c}
                active={c.contact_name === selected}
                onClick={() => setSelected(c.contact_name)} />
            ))}
          </div>
        </div>

        {/* 右：当前会话 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {!activeContact ? (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, fontSize: 18, opacity: .5 }}>
              选一位家人开始看 TA 的消息
            </div>
          ) : (
            <>
              <div style={{ padding: '18px 32px', borderBottom: `0.5px solid ${C.mist}22`, fontSize: 20, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, color: C.ink, letterSpacing: '.06em' }}>
                与 {activeContact.contact_name} 的消息
              </div>
              <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '20px 32px 24px' }}>
                {thread.length === 0 && (
                  <div style={{ textAlign: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, fontSize: 16, opacity: .5, marginTop: 80 }}>
                    还没有消息
                  </div>
                )}
                {thread.map(m => <ChatBubble key={m.id} m={m} isMine={m.role === 'patient'} />)}
              </div>
              <ReplyBar onSendText={sendText} onSendVoice={sendVoice} onPickVideo={sendVideo} disabled={busy} maxUploadMb={maxUploadMb} />
            </>
          )}
        </div>

      </div>
    </>
  );
}
