import { useCallback, useRef } from 'react';
import { DEVICE_ID } from '../constants';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

const messageSpeechText = (contactName, message) => {
  if (message.message_type === 'text') return `${contactName}说：${message.content || ''}`;
  if (message.message_type === 'photo') return `${contactName}发来一张照片。`;
  if (message.message_type === 'video') return `${contactName}发来一个视频。`;
  if (message.message_type === 'voice') return `${contactName}发来一段语音。`;
  return `${contactName}发来一条消息。`;
};

export default function useFamilyMessageReader({
  loadContacts,
  markThreadRead,
  pauseAssistantListening,
  resumeAssistantAndStart,
  speakViaTts,
  ttsPlaybackAbortRef,
}) {
  const mediaPlaybackRef = useRef(null);

  const stopPlayback = useCallback(() => {
    if (mediaPlaybackRef.current) {
      try {
        mediaPlaybackRef.current.pause();
        mediaPlaybackRef.current.src = '';
      } catch (_) { }
      mediaPlaybackRef.current = null;
    }
  }, []);

  const playAudioFile = useCallback((url) => new Promise((resolve) => {
    if (!url) { resolve(); return; }
    const audio = new Audio(url);
    mediaPlaybackRef.current = audio;
    audio.onended = () => { mediaPlaybackRef.current = null; resolve(); };
    audio.onerror = () => { mediaPlaybackRef.current = null; resolve(); };
    audio.play().catch(() => {
      mediaPlaybackRef.current = null;
      resolve();
    });
  }), []);

  const loadThreadMessages = useCallback(async (contactName, limit = 80, familyId = '') => {
    const params = new URLSearchParams({ device_id: DEVICE_ID, limit: String(limit) });
    if (familyId) params.set('family_id', familyId);
    else params.set('contact_name', contactName);
    const r = await fetch(`/api/hospice/messages?${params.toString()}`);
    const list = await r.json();
    return (Array.isArray(list) ? list : []).slice().reverse();
  }, []);

  const estimateSpeechMs = useCallback((text) => {
    const len = String(text || '').replace(/\s+/g, '').length;
    return Math.min(10000, Math.max(1200, len * 180));
  }, []);

  const waitForTts = useCallback(async (ms) => {
    let remaining = Math.max(0, ms || 0);
    while (remaining > 0 && !ttsPlaybackAbortRef.current) {
      const chunk = Math.min(200, remaining);
      await sleep(chunk);
      remaining -= chunk;
    }
  }, [ttsPlaybackAbortRef]);

  const speakAndWait = useCallback(async (text) => {
    const content = (text || '').trim();
    if (!content || ttsPlaybackAbortRef.current) return;
    await speakViaTts(content);
    if (ttsPlaybackAbortRef.current) return;
    await waitForTts(estimateSpeechMs(content));
  }, [estimateSpeechMs, speakViaTts, ttsPlaybackAbortRef, waitForTts]);

  const readFamilyMessages = useCallback(async (targetName) => {
    ttsPlaybackAbortRef.current = false;
    await pauseAssistantListening();
    stopPlayback();
    try {
      const latestContacts = await loadContacts();
      const normalizedTarget = (targetName || '').trim();
      let contact = null;
      if (normalizedTarget) {
        contact = latestContacts.find(c => c.contact_name && (
          c.contact_name === normalizedTarget ||
          c.contact_name.includes(normalizedTarget) ||
          normalizedTarget.includes(c.contact_name)
        ));
      }
      if (!contact) contact = latestContacts.find(c => (c.unread || 0) > 0);
      if (!contact && normalizedTarget) {
        await speakAndWait(`没有找到${normalizedTarget}的消息。`);
        return;
      }
      if (!contact) {
        await speakAndWait('现在没有新的家人消息。');
        return;
      }

      const messages = await loadThreadMessages(contact.contact_name, 80, contact.family_id || '');
      const familyMessages = messages.filter(m => (m.sender_role || 'family') === 'family');
      const unreadMessages = familyMessages.filter(m => !m.played);
      const messagesToRead = unreadMessages.length > 0 ? unreadMessages : familyMessages.slice(-3);
      if (messagesToRead.length === 0) {
        await speakAndWait(`${contact.contact_name}还没有发来消息。`);
        return;
      }

      await speakAndWait(`${contact.contact_name}给您发来${messagesToRead.length}条消息。`);
      for (const message of messagesToRead) {
        await speakAndWait(messageSpeechText(contact.contact_name, message));
        if (message.message_type === 'voice' && message.file_path) {
          await playAudioFile(message.file_path);
          await sleep(300);
        }
      }
      await markThreadRead(contact.contact_name, contact.family_id || '');
    } catch (err) {
      console.error('收听家属消息失败', err);
      await speakAndWait('消息暂时读不了，请稍后再试。');
    } finally {
      await resumeAssistantAndStart();
    }
  }, [loadContacts, loadThreadMessages, markThreadRead, pauseAssistantListening, playAudioFile, resumeAssistantAndStart, speakAndWait, stopPlayback, ttsPlaybackAbortRef]);

  const announceUnread = useCallback(async () => {
    ttsPlaybackAbortRef.current = false;
    await pauseAssistantListening();
    try {
      const latestContacts = await loadContacts();
      const unreadContacts = latestContacts.filter(c => (c.unread || 0) > 0);
      const total = unreadContacts.reduce((sum, c) => sum + (c.unread || 0), 0);
      if (total === 0) {
        await speakAndWait('现在没有新的家人消息。');
        return;
      }
      const names = unreadContacts.map(c => `${c.contact_name}${c.unread}条`).join('，');
      await speakAndWait(`您有${total}条新的家人消息，来自${names}。`);
    } finally {
      await resumeAssistantAndStart();
    }
  }, [loadContacts, pauseAssistantListening, resumeAssistantAndStart, speakAndWait, ttsPlaybackAbortRef]);

  return { announceUnread, readFamilyMessages, speakAndWait, stopPlayback };
}
