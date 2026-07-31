import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID, PATIENT_NAME } from '../constants';
import { fmtTime } from '../utils/time';
import ContactItem from '../components/ContactItem';
import ChatBubble from '../components/ChatBubble';
import ReplyBar from '../components/ReplyBar';

export default function InboxScreen({ contacts, refreshContacts, eventTick, maxUploadMb, onOpenContact, onUnbindContact }) {
  const [selected, setSelected] = useState(null);
  const [thread, setThread] = useState([]);
  const [busy, setBusy] = useState(false);
  const [unbindBusy, setUnbindBusy] = useState(false);
  const scrollRef = useRef(null);
  const contactKey = (contact) => contact?.family_id || contact?.contact_name || '';

  // 默认选中第一个联系人
  useEffect(() => {
    if (!selected && contacts.length > 0) {
      setSelected(contactKey(contacts[0]));
      return;
    }
    if (selected && !contacts.some(c => contactKey(c) === selected)) {
      setSelected(contacts.length > 0 ? contactKey(contacts[0]) : null);
      setThread([]);
    }
    // eslint-disable-next-line
  }, [contacts, selected]);

  const loadThread = async (name) => {
    if (!name) { setThread([]); return; }
    try {
      const active = contacts.find(c => contactKey(c) === name);
      const familyParam = active?.family_id
        ? `family_id=${encodeURIComponent(active.family_id)}`
        : `contact_name=${encodeURIComponent(name)}`;
      const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&${familyParam}&limit=200`);
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

  // 切联系人 → 拉消息；已读只由明确打开联系人或语音收听触发
  useEffect(() => {
    if (!selected) return;
    loadThread(selected);
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
    const active = contacts.find(c => contactKey(c) === selected);
    setBusy(true);
    try {
      await fetch('/api/hospice/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID, sender_role: 'patient', sender_name: PATIENT_NAME,
          family_id: active?.family_id, contact_name: active?.contact_name || selected, type: 'text', content,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送失败：' + e.message); }
    finally { setBusy(false); }
  };

  const sendVoice = async (blob, ext, secs) => {
    if (!selected) return;
    const active = contacts.find(c => contactKey(c) === selected);
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
          family_id: active?.family_id, contact_name: active?.contact_name || selected, type: 'voice',
          content: `语音 ${secs}s`, file_path: uj.url, duration_ms: secs * 1000,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送语音失败：' + e.message); }
    finally { setBusy(false); }
  };

  const sendMedia = async (file) => {
    if (!selected) return;
    const active = contacts.find(c => contactKey(c) === selected);
    const isVideo = file.type.startsWith('video/');
    const isImage = file.type.startsWith('image/');
    if (!isVideo && !isImage) {
      alert('请选择照片或视频');
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file, file.name || `${isVideo ? 'video' : 'photo'}-${Date.now()}`);
      const u = await fetch('/api/hospice/upload', { method: 'POST', body: fd });
      const uj = await u.json();
      if (!uj.success) throw new Error(uj.error || '上传失败');
      await fetch('/api/hospice/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID, sender_role: 'patient', sender_name: PATIENT_NAME,
          family_id: active?.family_id, contact_name: active?.contact_name || selected, type: isVideo ? 'video' : 'photo',
          content: file.name || (isVideo ? '视频' : '照片'), file_path: uj.url,
        }),
      });
      await loadThread(selected);
      refreshContacts && refreshContacts();
    } catch (e) { console.error(e); alert('发送媒体失败：' + e.message); }
    finally { setBusy(false); }
  };

  const activeContact = contacts.find(c => contactKey(c) === selected);

  const unbindActiveContact = async () => {
    if (!activeContact?.family_id || !onUnbindContact || unbindBusy) return;
    if (!window.confirm(`确定解除与 ${activeContact.contact_name} 的绑定吗？解除后对方需要重新配对才能继续联系。`)) return;
    setUnbindBusy(true);
    try {
      const ok = await onUnbindContact(activeContact.family_id);
      if (ok) {
        setThread([]);
        setSelected(null);
        refreshContacts && refreshContacts();
      }
    } finally {
      setUnbindBusy(false);
    }
  };

  return (
    <div style={{ position: 'relative', height: '100%', zIndex: 5, display: 'flex', animation: 'slideLeft .4s ease' }}>

      {/* 左：联系人列表 */}
      <div style={{ width: 260, flexShrink: 0, borderRight: `0.5px solid ${C.mist}33`, display: 'flex', flexDirection: 'column', background: 'rgba(255,250,242,0.46)' }}>
        <div style={{ padding: '18px 20px 12px', fontSize: 20, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: C.ink, letterSpacing: '.1em', borderBottom: `0.5px solid ${C.mist}22` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            家人
            <span style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.04em' }}>常驻消息</span>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {contacts.length === 0 ? (
            <div style={{ textAlign: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, fontSize: 16, lineHeight: 2, opacity: .78, marginTop: 60, padding: '0 20px' }}>
              还没有家人的消息<br />等家人发来问候
            </div>
          ) : contacts.map(c => (
            <ContactItem key={contactKey(c)} c={c}
              active={contactKey(c) === selected}
              onClick={() => {
                setSelected(contactKey(c));
                onOpenContact && onOpenContact(c.contact_name, c.family_id);
              }} />
          ))}
        </div>
      </div>

      {/* 右：当前会话 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {!activeContact ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, fontSize: 18, opacity: .78 }}>
            选一位家人开始看 TA 的消息
          </div>
        ) : (
          <>
            <div style={{ padding: '18px 28px', borderBottom: `0.5px solid ${C.mist}22`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <div style={{ fontSize: 20, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, color: C.ink, letterSpacing: '.06em' }}>
                与 {activeContact.contact_name} 的消息
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                {(activeContact.unread || 0) > 0 && (
                  <button onClick={() => onOpenContact && onOpenContact(activeContact.contact_name, activeContact.family_id)}
                    style={{ border: `1px solid ${C.amber}55`, background: `${C.amber}14`, color: C.amber, borderRadius: 14, padding: '6px 12px', fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' }}>
                    标记已听
                  </button>
                )}
                {activeContact.family_id && (
                  <button
                    onClick={unbindActiveContact}
                    disabled={unbindBusy}
                    style={{ border: `1px solid ${C.red}44`, background: `${C.red}10`, color: C.red, borderRadius: 14, padding: '6px 12px', fontSize: 12, fontFamily: 'Noto Sans SC', cursor: unbindBusy ? 'not-allowed' : 'pointer', opacity: unbindBusy ? .55 : 1 }}
                  >
                    {unbindBusy ? '解绑中' : '解绑'}
                  </button>
                )}
              </div>
            </div>
            <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '18px 28px 22px' }}>
              {thread.length === 0 && (
                <div style={{ textAlign: 'center', color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, fontSize: 16, opacity: .78, marginTop: 80 }}>
                  还没有消息
                </div>
              )}
              {thread.map(m => <ChatBubble key={m.id} m={m} isMine={m.role === 'patient'} />)}
            </div>
            <ReplyBar onSendText={sendText} onSendVoice={sendVoice} onPickMedia={sendMedia} disabled={busy} maxUploadMb={maxUploadMb} />
          </>
        )}
      </div>
    </div>
  );
}
