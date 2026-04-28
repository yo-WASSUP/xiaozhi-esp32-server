import { useCallback, useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from './constants';
import PaperBg from './components/PaperBg';
import TopBar from './components/TopBar';
import ConnectBar from './components/ConnectBar';
import ChatScreen from './screens/ChatScreen';
import InboxScreen from './screens/InboxScreen';
import IncomingCallOverlay from './components/IncomingCallOverlay';
import ActiveCallOverlay from './components/ActiveCallOverlay';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export default function App() {
  const [aiState, setAiState]     = useState('idle');
  const [msg, setMsg]             = useState(null);
  const [lastHeard, setLastHeard] = useState('');
  const [incoming, setIncoming]   = useState(null);   // {caller, callType}
  const [inCall, setInCall]       = useState(null);
  const [connected, setConnected] = useState(false);
  const [connectStatus, setConnectStatus] = useState('');
  const [recording, setRecording] = useState(false);
  const [micOk, setMicOk]         = useState(false);
  const [assistantHold, setAssistantHold] = useState(false);
  const [contacts, setContacts]   = useState([]);
  const [eventTick, setEventTick] = useState(0);
  const [maxUploadMb, setMaxUploadMb] = useState(50);

  const connectingRef = useRef(false);
  const initStartedRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const recordingRef = useRef(false);
  const connectedRef = useRef(false);
  const micOkRef = useRef(false);
  const assistantHoldRef = useRef(false);
  const inCallRef = useRef(null);
  const incomingRef = useRef(null);
  const mediaPlaybackRef = useRef(null);

  useEffect(() => { connectedRef.current = connected; }, [connected]);
  useEffect(() => { micOkRef.current = micOk; }, [micOk]);
  useEffect(() => { assistantHoldRef.current = assistantHold; }, [assistantHold]);
  useEffect(() => { inCallRef.current = inCall; }, [inCall]);
  useEffect(() => { incomingRef.current = incoming; }, [incoming]);

  // 拉一次配置（上传上限）
  useEffect(() => {
    fetch('/api/hospice/config')
      .then(r => r.json())
      .then(j => { if (j && j.upload_max_mb) setMaxUploadMb(j.upload_max_mb); })
      .catch(() => { });
  }, []);

  const unread = contacts.reduce((s, c) => s + (c.unread || 0), 0);

  const loadContacts = useCallback(async () => {
    try {
      const r = await fetch(`/api/hospice/contacts?device_id=${encodeURIComponent(DEVICE_ID)}`);
      const list = await r.json();
      const safeList = Array.isArray(list) ? list : [];
      setContacts(safeList);
      return safeList;
    } catch (e) { console.error('加载联系人失败', e); }
    return [];
  }, []);

  const markThreadRead = useCallback(async (contactName) => {
    if (!contactName) return;
    try {
      await fetch(`/api/hospice/thread/read?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(contactName)}`, { method: 'POST' });
      await loadContacts();
      setEventTick(t => t + 1);
    } catch (e) { console.error('标记已读失败', e); }
  }, [loadContacts]);

  const stopPlayback = useCallback(() => {
    try {
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    } catch (_) { }
    if (mediaPlaybackRef.current) {
      try {
        mediaPlaybackRef.current.pause();
        mediaPlaybackRef.current.src = '';
      } catch (_) { }
      mediaPlaybackRef.current = null;
    }
  }, []);

  const speakLocal = useCallback((text) => new Promise((resolve) => {
    if (!text) { resolve(); return; }
    if (!('speechSynthesis' in window)) {
      console.log('[patient] speech:', text);
      resolve();
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'zh-CN';
    utter.rate = 0.92;
    utter.pitch = 1;
    utter.onend = resolve;
    utter.onerror = resolve;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }), []);

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

  const pauseAssistantListening = useCallback(async () => {
    setAssistantHold(true);
    assistantHoldRef.current = true;
    if (recordingRef.current && window.XiaozhiClient) {
      try { await window.XiaozhiClient.stopRecording(); } catch (_) { }
      recordingRef.current = false;
      setRecording(false);
    }
  }, []);

  const resumeAssistantListening = useCallback(() => {
    setAssistantHold(false);
    assistantHoldRef.current = false;
  }, []);

  const startListening = useCallback(async () => {
    if (!window.XiaozhiClient || recordingRef.current || !connectedRef.current || !micOkRef.current) return;
    if (assistantHoldRef.current || inCallRef.current) return;
    try {
      const ok = await window.XiaozhiClient.startRecording();
      recordingRef.current = !!ok;
      setRecording(!!ok);
      if (!ok) setConnectStatus('麦克风没有开始工作，请点“重新连接”重试');
    } catch (err) {
      console.error('自动拾音失败', err);
      recordingRef.current = false;
      setRecording(false);
      setConnectStatus('麦克风启动失败：' + (err?.message || '未知错误'));
    }
  }, []);

  const connectXiaozhi = useCallback(async () => {
    if (!window.XiaozhiClient || connectingRef.current || connectedRef.current) return;
    connectingRef.current = true;
    setConnectStatus('正在连接小暖...');
    try {
      const ok = await Promise.race([
        window.XiaozhiClient.connect(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('CONNECT_TIMEOUT')), 10000)),
      ]);
      if (!ok) throw new Error('CONNECT_FAILED');
      setConnectStatus('');
    } catch (err) {
      console.error('connect failed', err);
      setConnectStatus(err?.message === 'CONNECT_TIMEOUT' ? '连接超时，正在自动重试' : '连接失败，正在自动重试');
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connectXiaozhi();
      }, 3000);
    } finally {
      connectingRef.current = false;
    }
  }, []);

  const scheduleReconnect = useCallback((delay = 2500) => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      connectXiaozhi();
    }, delay);
  }, [connectXiaozhi]);

  const handleManualConnect = useCallback(async () => {
    if (!window.XiaozhiClient) {
      setConnectStatus('连接模块还没有加载完成，请刷新页面后重试');
      return;
    }
    try {
      const ok = await window.XiaozhiClient.init();
      setMicOk(!!ok);
      micOkRef.current = !!ok;
      if (!ok) {
        setConnectStatus('请允许麦克风权限后重试');
        return;
      }
      await connectXiaozhi();
    } catch (err) {
      setConnectStatus('连接模块初始化失败：' + (err?.message || '未知错误'));
    }
  }, [connectXiaozhi]);

  const loadThreadMessages = useCallback(async (contactName, limit = 80) => {
    const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(contactName)}&limit=${limit}`);
    const list = await r.json();
    return (Array.isArray(list) ? list : []).slice().reverse();
  }, []);

  const messageSpeechText = (contactName, message) => {
    if (message.message_type === 'text') return `${contactName}说：${message.content || ''}`;
    if (message.message_type === 'photo') return `${contactName}发来一张照片。`;
    if (message.message_type === 'video') return `${contactName}发来一个视频。`;
    if (message.message_type === 'voice') return `${contactName}发来一段语音。`;
    return `${contactName}发来一条消息。`;
  };

  const readFamilyMessages = useCallback(async (targetName) => {
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
        await speakLocal(`没有找到${normalizedTarget}的消息。`);
        return;
      }
      if (!contact) {
        await speakLocal('现在没有新的家人消息。');
        return;
      }

      const messages = await loadThreadMessages(contact.contact_name);
      const familyMessages = messages.filter(m => (m.sender_role || 'family') === 'family');
      const unreadMessages = familyMessages.filter(m => !m.played);
      const messagesToRead = unreadMessages.length > 0 ? unreadMessages : familyMessages.slice(-3);
      if (messagesToRead.length === 0) {
        await speakLocal(`${contact.contact_name}还没有发来消息。`);
        return;
      }

      await speakLocal(`${contact.contact_name}给您发来${messagesToRead.length}条消息。`);
      for (const message of messagesToRead) {
        await speakLocal(messageSpeechText(contact.contact_name, message));
        if (message.message_type === 'voice' && message.file_path) {
          await playAudioFile(message.file_path);
          await sleep(300);
        }
      }
      await markThreadRead(contact.contact_name);
    } catch (err) {
      console.error('收听家属消息失败', err);
      await speakLocal('消息暂时读不了，请稍后再试。');
    } finally {
      resumeAssistantListening();
    }
  }, [loadContacts, loadThreadMessages, markThreadRead, pauseAssistantListening, playAudioFile, resumeAssistantListening, speakLocal, stopPlayback]);

  const announceUnread = useCallback(async () => {
    await pauseAssistantListening();
    try {
      const latestContacts = await loadContacts();
      const unreadContacts = latestContacts.filter(c => (c.unread || 0) > 0);
      const total = unreadContacts.reduce((sum, c) => sum + (c.unread || 0), 0);
      if (total === 0) {
        await speakLocal('现在没有新的家人消息。');
        return;
      }
      const names = unreadContacts.map(c => `${c.contact_name}${c.unread}条`).join('，');
      await speakLocal(`您有${total}条新的家人消息，来自${names}。`);
    } finally {
      resumeAssistantListening();
    }
  }, [loadContacts, pauseAssistantListening, resumeAssistantListening, speakLocal]);

  // 联系人列表 + SSE 订阅
  useEffect(() => {
    loadContacts();
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    const bump = () => { loadContacts(); setEventTick(t => t + 1); };
    es.addEventListener('message.new', bump);
    es.addEventListener('message.read', bump);
    es.onerror = () => { /* 浏览器自动重连 */ };
    return () => es.close();
  }, [loadContacts]);

  // 桥接 XiaozhiClient 事件（connection / state / llm / stt / ready）
  useEffect(() => {
    const onConn  = e => {
      const isConnected = !!e.detail.connected;
      setConnected(isConnected);
      connectedRef.current = isConnected;
      if (!isConnected) {
        recordingRef.current = false;
        setRecording(false);
        scheduleReconnect();
      }
    };
    const onState = e => setAiState(e.detail.state);
    const onLlm   = e => setMsg(e.detail.text);
    const onStt   = e => setLastHeard(e.detail?.text || '');
    const onErr   = e => setConnectStatus(e.detail?.message || e.detail?.error?.message || '连接模块初始化失败');
    const onReady = async () => {
      if (initStartedRef.current) return;
      initStartedRef.current = true;
      try {
        const ok = await window.XiaozhiClient.init();
        setMicOk(!!ok);
        micOkRef.current = !!ok;
        if (ok) connectXiaozhi();
        else setConnectStatus('请允许麦克风权限后重试');
      } catch (err) {
        console.error('XiaozhiClient init 失败', err);
        setConnectStatus('连接模块初始化失败：' + (err?.message || '未知错误'));
      }
    };
    window.addEventListener('xz:connection', onConn);
    window.addEventListener('xz:state', onState);
    window.addEventListener('xz:llm', onLlm);
    window.addEventListener('xz:stt', onStt);
    window.addEventListener('xz:error', onErr);
    window.addEventListener('xz:ready', onReady);
    if (window.XiaozhiClient) onReady();
    return () => {
      window.removeEventListener('xz:connection', onConn);
      window.removeEventListener('xz:state', onState);
      window.removeEventListener('xz:llm', onLlm);
      window.removeEventListener('xz:stt', onStt);
      window.removeEventListener('xz:error', onErr);
      window.removeEventListener('xz:ready', onReady);
    };
  }, [connectXiaozhi, scheduleReconnect]);

  useEffect(() => {
    if (connected && micOk && !assistantHold && !inCall) startListening();
  }, [assistantHold, connected, inCall, micOk, startListening]);

  useEffect(() => () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    stopPlayback();
  }, [stopPlayback]);

  // ── 通话（WebRTC） ──
  const callRef = useRef(null);
  const [localStream, setLocalStream]   = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);

  useEffect(() => {
    const client = new window.CallClient({
      deviceId: DEVICE_ID,
      role: 'patient',
      onIncoming: ({ fromName, callType }) => {
        setIncoming({
          caller: { from: fromName || '家人', avatar: '👤' },
          callType,
        });
      },
      onLocalStream:  (s) => setLocalStream(s),
      onRemoteStream: (s) => setRemoteStream(s),
      onState: (s) => {
        // 状态 connecting / active 时：把来电浮层切换为通话浮层
        if (s === 'connecting' || s === 'active') {
          pauseAssistantListening();
          setIncoming(prev => {
            if (prev) {
              setInCall({ caller: prev.caller, callType: prev.callType });
              return null;
            }
            return null;
          });
        }
      },
      onEnded: () => {
        setIncoming(null);
        setInCall(null);
        setLocalStream(null);
        setRemoteStream(null);
        resumeAssistantListening();
      },
    });
    callRef.current = client;
    client.connect();
    return () => {
      try {
        client.hangup();
        if (typeof client.disconnect === 'function') client.disconnect();
      } catch (_) { }
    };
  }, [pauseAssistantListening, resumeAssistantListening]);

  const acceptCall  = async () => {
    if (!callRef.current || !incomingRef.current) {
      await speakLocal('现在没有来电。');
      return;
    }
    await pauseAssistantListening();
    callRef.current.accept();
  };
  const declineCall = () => { callRef.current && callRef.current.reject(); setIncoming(null); };
  const endCall     = () => callRef.current && callRef.current.hangup();
  const toggleMute   = (v) => callRef.current && callRef.current.toggleMute(v);
  const toggleCamera = (v) => callRef.current && callRef.current.toggleCamera(v);

  useEffect(() => {
    const onClientAction = async (e) => {
      const detail = e.detail || {};
      const action = detail.action;
      if (!action) return;
      setAiState('idle');
      if (action === 'accept_call') {
        await acceptCall();
      } else if (action === 'reject_call') {
        if (incomingRef.current) {
          declineCall();
          await speakLocal('已经帮您拒接。');
        } else {
          await speakLocal('现在没有来电。');
        }
      } else if (action === 'hangup_call') {
        if (inCallRef.current) {
          endCall();
        } else if (incomingRef.current) {
          declineCall();
          await speakLocal('已经挂掉来电。');
        } else {
          await speakLocal('现在没有正在进行的通话。');
        }
      } else if (action === 'read_family_messages') {
        await readFamilyMessages(detail.contact_name || detail.target_name || '');
      } else if (action === 'announce_unread') {
        await announceUnread();
      } else if (action === 'stop_playback') {
        stopPlayback();
        resumeAssistantListening();
      }
    };
    window.addEventListener('xz:client-action', onClientAction);
    return () => window.removeEventListener('xz:client-action', onClientAction);
  }, [announceUnread, readFamilyMessages, resumeAssistantListening, speakLocal, stopPlayback]);

  return (
    <PaperBg>
      <TopBar connected={connected} recording={recording} unread={unread} micOk={micOk} connectStatus={connectStatus} />
      <main style={{
        position: 'absolute',
        top: 72,
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 5,
        display: 'grid',
        gridTemplateColumns: 'minmax(470px, 45%) minmax(620px, 55%)',
        gap: 0,
        overflow: 'hidden',
      }}>
        <section style={{ position: 'relative', minWidth: 0, borderRight: '0.5px solid rgba(143,163,176,0.22)', overflow: 'hidden' }}>
          <ChatScreen aiState={aiState} msg={msg} lastHeard={lastHeard} connected={connected} recording={recording} />
        </section>
        <section style={{ position: 'relative', minWidth: 0, overflow: 'hidden', background: 'rgba(255,250,242,0.28)' }}>
          <InboxScreen contacts={contacts} refreshContacts={loadContacts} eventTick={eventTick} maxUploadMb={maxUploadMb} onOpenContact={markThreadRead} />
        </section>
      </main>

      {(!connected || !micOk || connectStatus) && (
        <ConnectBar
          connected={connected} onConnect={handleManualConnect} recording={recording} micOk={micOk}
          connectStatus={connectStatus}
        />
      )}

      {incoming && (
        <IncomingCallOverlay caller={incoming.caller} callType={incoming.callType}
          onAccept={acceptCall} onDecline={declineCall} />
      )}
      {inCall && (
        <ActiveCallOverlay caller={inCall.caller} callType={inCall.callType}
          onEnd={endCall}
          localStream={localStream} remoteStream={remoteStream}
          onToggleMute={toggleMute} onToggleCamera={toggleCamera} />
      )}
    </PaperBg>
  );
}
