import { useCallback, useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from './constants';
import PaperBg from './components/PaperBg';
import TopBar from './components/TopBar';
import ConnectBar from './components/ConnectBar';
import ChatScreen from './screens/ChatScreen';
import InboxScreen from './screens/InboxScreen';
import DignityDebugPanel from './screens/DignityDebugPanel';
import IncomingCallOverlay from './components/IncomingCallOverlay';
import ActiveCallOverlay from './components/ActiveCallOverlay';
import SettingsPanel from './components/SettingsPanel';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export default function App() {
  const [aiState, setAiState]     = useState('idle');
  const [msg, setMsg]             = useState(null);
  const [lastHeard, setLastHeard] = useState('');
  const [incoming, setIncoming]   = useState(null);   // {caller, callType}
  const [inCall, setInCall]       = useState(null);
  const [callState, setCallState] = useState('idle');
  const [connected, setConnected] = useState(false);
  const [connectStatus, setConnectStatus] = useState('');
  const [recording, setRecording] = useState(false);
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [micOk, setMicOk]         = useState(false);
  const [assistantHold, setAssistantHold] = useState(false);
  const [contacts, setContacts]   = useState([]);
  const [eventTick, setEventTick] = useState(0);
  const [maxUploadMb, setMaxUploadMb] = useState(50);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [dignityMode, setDignityMode] = useState(false);
  const [dignityStatus, setDignityStatus] = useState(null);
  const [dignityOpeningReply, setDignityOpeningReply] = useState('');
  const [dignityTurns, setDignityTurns] = useState([]);
  const [dignityDebugBusy, setDignityDebugBusy] = useState(false);
  const [dignityDocumentBusy, setDignityDocumentBusy] = useState(false);
  const [dignityDocumentConfirmBusy, setDignityDocumentConfirmBusy] = useState(false);
  const [dignityDocument, setDignityDocument] = useState('');
  const [dignityDocumentUrl, setDignityDocumentUrl] = useState('');
  const [dignityVoiceMode, setDignityVoiceMode] = useState(false);

  const connectingRef = useRef(false);
  const initStartedRef = useRef(false);
  const reconnectTimerRef = useRef(null);
  const callStateTimerRef = useRef(null);
  const callCommandRecognizerRef = useRef(null);
  const callCommandRecognizerActiveRef = useRef(false);
  const recordingRef = useRef(false);
  const userSpeakingRef = useRef(false);
  const connectedRef = useRef(false);
  const micOkRef = useRef(false);
  const assistantHoldRef = useRef(false);
  const inCallRef = useRef(null);
  const incomingRef = useRef(null);
  const callStateRef = useRef('idle');
  const dignityModeRef = useRef(false);
  const dignityLiveTurnStartedAtRef = useRef(null);
  const dignityDebugTurnStartedAtRef = useRef(null);
  const mediaPlaybackRef = useRef(null);
  const ttsPlaybackAbortRef = useRef(false);
  const speakingFallbackTimerRef = useRef(null);

  useEffect(() => { connectedRef.current = connected; }, [connected]);
  useEffect(() => { userSpeakingRef.current = userSpeaking; }, [userSpeaking]);
  useEffect(() => { micOkRef.current = micOk; }, [micOk]);
  useEffect(() => { assistantHoldRef.current = assistantHold; }, [assistantHold]);
  useEffect(() => { inCallRef.current = inCall; }, [inCall]);
  useEffect(() => { incomingRef.current = incoming; }, [incoming]);
  useEffect(() => { callStateRef.current = callState; }, [callState]);
  useEffect(() => { dignityModeRef.current = dignityMode; }, [dignityMode]);

  // 鎷変竴娆￠厤缃紙涓婁紶涓婇檺锛?
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
    } catch (e) { console.error('load contacts failed', e); }
    return [];
  }, []);

  const markThreadRead = useCallback(async (contactName) => {
    if (!contactName) return;
    try {
      await fetch(`/api/hospice/thread/read?device_id=${encodeURIComponent(DEVICE_ID)}&contact_name=${encodeURIComponent(contactName)}`, { method: 'POST' });
      await loadContacts();
      setEventTick(t => t + 1);
    } catch (e) { console.error('鏍囪宸茶澶辫触', e); }
  }, [loadContacts]);

  const stopPlayback = useCallback(() => {
    if (mediaPlaybackRef.current) {
      try {
        mediaPlaybackRef.current.pause();
        mediaPlaybackRef.current.src = '';
      } catch (_) { }
      mediaPlaybackRef.current = null;
    }
  }, []);

  const stopTtsPlayback = useCallback(async () => {
    ttsPlaybackAbortRef.current = true;
    try {
      await fetch('/api/hospice/tts/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID }),
      });
    } catch (e) {
      console.error('鍋滄TTS澶辫触', e);
    }
  }, []);

  const speakViaTts = useCallback(async (text) => {
    const content = (text || '').trim();
    if (!content) return false;
    try {
      const r = await fetch('/api/hospice/tts/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, text: content }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.error || `HTTP ${r.status}`);
      }
      return true;
    } catch (e) {
      console.error('TTS鎾姤澶辫触', e);
      return false;
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

  const pauseAssistantListening = useCallback(async () => {
    setAssistantHold(true);
    assistantHoldRef.current = true;
    if (recordingRef.current && window.XiaozhiClient) {
      try { await window.XiaozhiClient.stopRecording(); } catch (_) { }
      recordingRef.current = false;
      setRecording(false);
      userSpeakingRef.current = false;
      setUserSpeaking(false);
      setAiState('idle');
    }
  }, []);

  const resumeAssistantListening = useCallback(() => {
    setAssistantHold(false);
    assistantHoldRef.current = false;
  }, []);

  const startListening = useCallback(async ({ allowInCall = false } = {}) => {
    if (!window.XiaozhiClient || recordingRef.current || !connectedRef.current || !micOkRef.current) return;
    if (!allowInCall && (assistantHoldRef.current || inCallRef.current)) return;
    try {
      const ok = await window.XiaozhiClient.startRecording({ callActive: allowInCall });
      const active = !!ok || !!window.XiaozhiClient.isRecording?.();
      recordingRef.current = active;
      setRecording(active);
      if (active) {
        setAiState('idle');
        setConnectStatus('');
      }
      if (!ok) setConnectStatus('麦克风没有开始工作，请重新连接后再试');
      if (active) setConnectStatus('');
    } catch (err) {
      console.error('鑷姩鎷鹃煶澶辫触', err);
      recordingRef.current = false;
      setRecording(false);
      userSpeakingRef.current = false;
      setUserSpeaking(false);
      setAiState('idle');
      setConnectStatus('麦克风启动失败：' + (err?.message || '未知错误'));
    }
  }, []);

  const resumeAssistantAndStart = useCallback(async ({ allowInCall = false, delay = 200 } = {}) => {
    resumeAssistantListening();
    await sleep(delay);
    await startListening({ allowInCall });
  }, [resumeAssistantListening, startListening]);

  const sendClientState = useCallback(async (payload) => {
    if (!window.XiaozhiClient || typeof window.XiaozhiClient.sendClientState !== 'function') return false;
    try {
      return await window.XiaozhiClient.sendClientState(payload);
    } catch (_) {
      return false;
    }
  }, []);

  const sendDignityAction = useCallback(async (action, payload = {}) => {
    if (!window.XiaozhiClient || typeof window.XiaozhiClient.sendDignityAction !== 'function') return false;
    try {
      return await window.XiaozhiClient.sendDignityAction(action, payload);
    } catch (_) {
      return false;
    }
  }, []);

  const toggleDignityMode = useCallback(async () => {
    if (!connectedRef.current) {
      setConnectStatus('璇峰厛杩炴帴灏忔殩锛屽啀鍒囨崲灏婁弗鐤楁硶妯″紡');
      return;
    }
    const nextAction = dignityMode ? 'stop' : 'start';
    const ok = await sendDignityAction(nextAction, { patient_id: DEVICE_ID });
    if (!ok) setConnectStatus('灏婁弗鐤楁硶妯″紡鍒囨崲澶辫触锛岃绋嶅悗鍐嶈瘯');
  }, [dignityMode, sendDignityAction]);

  const runDignityDebugTurn = useCallback(async (text) => {
    setDignityDebugBusy(true);
    dignityDebugTurnStartedAtRef.current = performance.now();
    const ok = await sendDignityAction('debug_turn', { text });
    if (!ok) {
      dignityDebugTurnStartedAtRef.current = null;
      setDignityDebugBusy(false);
      setConnectStatus('尊严疗法调试发送失败');
    }
  }, [sendDignityAction]);

  const resetDignityDebug = useCallback(async () => {
    setDignityTurns([]);
    setDignityDocument('');
    setDignityDocumentUrl('');
    setDignityDocumentConfirmBusy(false);
    const ok = await sendDignityAction('debug_reset');
    if (!ok) setConnectStatus('尊严疗法调试重置失败');
  }, [sendDignityAction]);


  const normalizeCommandText = (text) => String(text || '').replace(/[\s锛屻€傦紒锛熴€?.!?]/g, '');

  const generateDignityDocument = useCallback(async () => {
    setDignityDocumentBusy(true);
    setDignityDocumentConfirmBusy(false);
    setDignityDocumentUrl('');
    const ok = await sendDignityAction('generate_document', { patient_id: DEVICE_ID });
    if (!ok) {
      setDignityDocumentBusy(false);
      setConnectStatus('生命访谈文档生成请求发送失败');
    }
  }, [sendDignityAction]);

  const confirmDignityDocument = useCallback(async (documentText) => {
    const document = String(documentText || '').trim();
    if (!document) {
      setConnectStatus('请先生成并确认文档内容');
      return;
    }
    setDignityDocumentConfirmBusy(true);
    const ok = await sendDignityAction('confirm_document', { patient_id: DEVICE_ID, document });
    if (!ok) {
      setDignityDocumentConfirmBusy(false);
      setConnectStatus('生命访谈 Word 保存请求发送失败');
    }
  }, [sendDignityAction]);

  const toggleDignityVoiceMode = useCallback(async () => {
    if (!dignityMode) return;
    if (dignityVoiceMode) {
      setDignityVoiceMode(false);
      await pauseAssistantListening();
      return;
    }
    if (!connectedRef.current || !micOkRef.current) {
      setConnectStatus('请先连接并允许麦克风权限，再开始语音访谈');
      return;
    }
    setDignityVoiceMode(true);
    await resumeAssistantAndStart();
  }, [dignityMode, dignityVoiceMode, pauseAssistantListening, resumeAssistantAndStart]);

  const isHangupCommand = (text) => {
    const value = normalizeCommandText(text);
    return [
      '挂电话',
      '挂断电话',
      '挂掉电话',
      '结束通话',
      '挂了电话',
      '挂掉',
      '挂断',
      '挂了',
    ].some(phrase => value.includes(phrase));
  };

  const stopCallCommandRecognizer = useCallback(() => {
    callCommandRecognizerActiveRef.current = false;
    const recognizer = callCommandRecognizerRef.current;
    callCommandRecognizerRef.current = null;
    if (recognizer) {
      try {
        recognizer.onend = null;
        recognizer.stop();
      } catch (_) { }
    }
  }, []);

  const setCallCommandMode = useCallback(async (active) => {
    if (callStateTimerRef.current) {
      clearInterval(callStateTimerRef.current);
      callStateTimerRef.current = null;
    }
    await sendClientState({ call_active: active });
    if (active) {
      callStateTimerRef.current = setInterval(() => {
        sendClientState({ call_active: true });
      }, 2000);
    }
  }, [sendClientState]);

  const endCallRef = useRef(null);

  const startCallCommandRecognizer = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || callCommandRecognizerActiveRef.current) return;

    const recognizer = new SpeechRecognition();
    recognizer.lang = 'zh-CN';
    recognizer.continuous = true;
    recognizer.interimResults = true;
    recognizer.maxAlternatives = 3;
    callCommandRecognizerActiveRef.current = true;
    callCommandRecognizerRef.current = recognizer;

    recognizer.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        for (let j = 0; j < result.length; j += 1) {
          const text = result[j]?.transcript || '';
          if (isHangupCommand(text)) {
            stopCallCommandRecognizer();
            if (endCallRef.current) endCallRef.current();
            return;
          }
        }
      }
    };
    recognizer.onerror = () => { };
    recognizer.onend = () => {
      if (callCommandRecognizerActiveRef.current && (callStateRef.current === 'active' || inCallRef.current)) {
        try { recognizer.start(); } catch (_) { }
      }
    };

    try {
      recognizer.start();
    } catch (_) {
      callCommandRecognizerActiveRef.current = false;
      callCommandRecognizerRef.current = null;
    }
  }, [stopCallCommandRecognizer]);

  const connectXiaozhi = useCallback(async () => {
    if (!window.XiaozhiClient || connectingRef.current || connectedRef.current) return;
    connectingRef.current = true;
    setConnectStatus('姝ｅ湪杩炴帴灏忔殩...');
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
  }, []);

  const speakAndWait = useCallback(async (text) => {
    const content = (text || '').trim();
    if (!content || ttsPlaybackAbortRef.current) return;
    await speakViaTts(content);
    if (ttsPlaybackAbortRef.current) return;
    await waitForTts(estimateSpeechMs(content));
  }, [estimateSpeechMs, speakViaTts, waitForTts]);

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

      const messages = await loadThreadMessages(contact.contact_name);
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
      await markThreadRead(contact.contact_name);
    } catch (err) {
      console.error('鏀跺惉瀹跺睘娑堟伅澶辫触', err);
      await speakAndWait('消息暂时读不了，请稍后再试。');
    } finally {
      await resumeAssistantAndStart();
    }
  }, [loadContacts, loadThreadMessages, markThreadRead, pauseAssistantListening, playAudioFile, resumeAssistantAndStart, speakAndWait, stopPlayback]);

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
  }, [loadContacts, pauseAssistantListening, resumeAssistantAndStart, speakAndWait]);

  // 鑱旂郴浜哄垪琛?+ SSE 璁㈤槄
  useEffect(() => {
    loadContacts();
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    const bump = () => { loadContacts(); setEventTick(t => t + 1); };
    es.addEventListener('message.new', bump);
    es.addEventListener('message.read', bump);
    es.onerror = () => { /* 娴忚鍣ㄨ嚜鍔ㄩ噸杩?*/ };
    return () => es.close();
  }, [loadContacts]);

  // 妗ユ帴 XiaozhiClient 浜嬩欢锛坈onnection / state / llm / stt / ready锛?
  useEffect(() => {
    const onConn  = e => {
      const isConnected = !!e.detail.connected;
      setConnected(isConnected);
      connectedRef.current = isConnected;
      if (!isConnected) {
        recordingRef.current = false;
        setRecording(false);
        userSpeakingRef.current = false;
        setUserSpeaking(false);
        scheduleReconnect();
      }
    };
    const onState = e => {
      const nextState = e.detail?.state;
      if (speakingFallbackTimerRef.current) {
        clearTimeout(speakingFallbackTimerRef.current);
        speakingFallbackTimerRef.current = null;
      }
      if (nextState === 'speaking') {
        setAiState('speaking');
        speakingFallbackTimerRef.current = setTimeout(() => {
          speakingFallbackTimerRef.current = null;
          setAiState('idle');
        }, 18000);
      } else if (nextState === 'idle') {
        setAiState('idle');
      } else if (nextState) {
        setAiState(nextState);
      }
    };
    const onLlm   = e => {
      if (callStateRef.current === 'active' || inCallRef.current) {
        stopTtsPlayback();
        return;
      }
      setMsg(e.detail.text);
    };
    const attachClientLatency = (payload, startedAtRef) => {
      const startedAt = startedAtRef.current;
      if (!startedAt) return payload;
      startedAtRef.current = null;
      return {
        ...payload,
        client_response_latency_ms: Math.max(0, Math.round(performance.now() - startedAt)),
      };
    };
    const onStt = e => {
      setLastHeard(e.detail?.text || '');
      setUserSpeaking(false);
      userSpeakingRef.current = false;
      setAiState('speaking');
      if (dignityModeRef.current) {
        dignityLiveTurnStartedAtRef.current = performance.now();
      }
    };
    const onVoiceActivity = e => {
      const active = !!e.detail?.active;
      setUserSpeaking(active);
      userSpeakingRef.current = active;
    };
    const onErr = e => setConnectStatus(e.detail?.message || e.detail?.error?.message || '连接模块初始化失败');
    const onDignity = e => {
      const detail = e.detail || {};
      const event = detail.event;
      const data = detail.data || {};
      if (event === 'mode_started') {
        setDignityMode(true);
        setDignityVoiceMode(false);
        setDignityStatus(data);
        setDignityOpeningReply(data.reply || '');
        if (data.reply) setMsg(data.reply);
        void pauseAssistantListening();
      } else if (event === 'mode_stopped') {
        setDignityMode(false);
        setDignityVoiceMode(false);
        setDignityStatus(data);
        void resumeAssistantAndStart();
      } else if (event === 'turn_result' || event === 'nurse_alert') {
        const nextData = attachClientLatency(data, dignityLiveTurnStartedAtRef);
        setDignityStatus(nextData);
        setDignityTurns(items => [...items, nextData]);
        if (nextData.reply) setMsg(nextData.reply);
      } else if (event === 'state_updated') {
        setDignityStatus(prev => ({
          ...data,
          client_response_latency_ms: data.client_response_latency_ms ?? prev?.client_response_latency_ms,
        }));
        setDignityTurns(items => {
          if (!items.length) return items;
          return items.map((item, index) => (
            index === items.length - 1 ? { ...item, ...data } : item
          ));
        });
      } else if (event === 'debug_turn_result') {
        const nextData = attachClientLatency(data, dignityDebugTurnStartedAtRef);
        setDignityDebugBusy(false);
        setDignityStatus(nextData);
        setDignityTurns(items => [...items, nextData]);
      } else if (event === 'debug_state_updated') {
        setDignityStatus(prev => ({
          ...data,
          client_response_latency_ms: data.client_response_latency_ms ?? prev?.client_response_latency_ms,
        }));
        setDignityTurns(items => {
          if (!items.length) return items;
          return items.map((item, index) => (
            index === items.length - 1 ? { ...item, ...data } : item
          ));
        });
      } else if (event === 'debug_reset') {
        setDignityDebugBusy(false);
        setDignityTurns([]);
        setDignityStatus(data);
        setDignityOpeningReply(data.reply || '');
        if (data.reply) setMsg(data.reply);
      } else if (event === 'document_started') {
        setDignityDocumentBusy(true);
        setDignityDocumentConfirmBusy(false);
      } else if (event === 'document_complete') {
        setDignityDocumentBusy(false);
        setDignityDocument(data.document || '');
        setDignityDocumentUrl('');
        if (data.dignity_memory) {
          setDignityStatus(prev => ({ ...(prev || {}), dignity_memory: data.dignity_memory }));
        }
      } else if (event === 'document_confirm_started') {
        setDignityDocumentConfirmBusy(true);
      } else if (event === 'document_confirmed') {
        setDignityDocumentConfirmBusy(false);
        setDignityDocument(data.document || '');
        setDignityDocumentUrl(data.document_url || '');
      } else if (event === 'document_error') {
        setDignityDocumentBusy(false);
        setDignityDocumentConfirmBusy(false);
        setDignityDocumentUrl('');
        setConnectStatus(data.message || '鐢熷懡璁胯皥鏂囨。鐢熸垚澶辫触');
      } else if (event === 'error') {
        dignityLiveTurnStartedAtRef.current = null;
        dignityDebugTurnStartedAtRef.current = null;
        setDignityDebugBusy(false);
        setDignityDocumentBusy(false);
        setDignityDocumentConfirmBusy(false);
        setConnectStatus(data.message || '灏婁弗鐤楁硶妯″紡澶勭悊澶辫触');
      }
    };
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
        console.error('XiaozhiClient init 澶辫触', err);
        setConnectStatus('连接模块初始化失败：' + (err?.message || '未知错误'));
      }
    };
    window.addEventListener('xz:connection', onConn);
    window.addEventListener('xz:state', onState);
    window.addEventListener('xz:llm', onLlm);
    window.addEventListener('xz:stt', onStt);
    window.addEventListener('xz:voice-activity', onVoiceActivity);
    window.addEventListener('xz:error', onErr);
    window.addEventListener('xz:dignity', onDignity);
    window.addEventListener('xz:ready', onReady);
    if (window.XiaozhiClient) onReady();
    return () => {
      window.removeEventListener('xz:connection', onConn);
      window.removeEventListener('xz:state', onState);
      window.removeEventListener('xz:llm', onLlm);
      window.removeEventListener('xz:stt', onStt);
      window.removeEventListener('xz:voice-activity', onVoiceActivity);
      window.removeEventListener('xz:error', onErr);
      window.removeEventListener('xz:dignity', onDignity);
      window.removeEventListener('xz:ready', onReady);
    };
  }, [connectXiaozhi, pauseAssistantListening, resumeAssistantAndStart, scheduleReconnect, stopTtsPlayback]);

  useEffect(() => {
    if (connected && micOk && !assistantHold && !inCall && (!dignityMode || dignityVoiceMode)) startListening();
  }, [assistantHold, connected, dignityMode, dignityVoiceMode, inCall, micOk, startListening]);

  useEffect(() => {
    if (dignityMode && !dignityVoiceMode) pauseAssistantListening();
  }, [dignityMode, dignityVoiceMode, pauseAssistantListening]);

  useEffect(() => {
    if (settingsOpen) {
      pauseAssistantListening();
    } else {
      resumeAssistantListening();
    }
  }, [pauseAssistantListening, resumeAssistantListening, settingsOpen]);

  useEffect(() => () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (callStateTimerRef.current) clearInterval(callStateTimerRef.current);
    if (speakingFallbackTimerRef.current) clearTimeout(speakingFallbackTimerRef.current);
    stopCallCommandRecognizer();
    stopPlayback();
  }, [stopCallCommandRecognizer, stopPlayback]);

  // 鈹€鈹€ 閫氳瘽锛圵ebRTC锛?鈹€鈹€
  const callRef = useRef(null);
  const [localStream, setLocalStream]   = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);

  useEffect(() => {
    const client = new window.CallClient({
      deviceId: DEVICE_ID,
      role: 'patient',
      onIncoming: ({ fromName, callType }) => {
        setIncoming({
          caller: { from: fromName || '瀹朵汉', avatar: '馃懁' },
          callType,
        });
        setCallState('incoming');
        resumeAssistantAndStart();
      },
      onLocalStream:  (s) => setLocalStream(s),
      onRemoteStream: (s) => setRemoteStream(s),
      onState: (s) => {
        // 鐘舵€?connecting / active 鏃讹細鎶婃潵鐢垫诞灞傚垏鎹负閫氳瘽娴眰
        if (s === 'connecting' || s === 'active') {
          pauseAssistantListening().finally(async () => {
            await setCallCommandMode(true);
            startCallCommandRecognizer();
          });
          const caller = incomingRef.current?.caller || inCallRef.current?.caller || { from: '通话中', avatar: '电话' };
          const callType = incomingRef.current?.callType || inCallRef.current?.callType || 'audio';
          setCallState('active');
          setInCall({ caller, callType });
          setIncoming(null);
        }
      },
      onEnded: () => {
        setIncoming(null);
        setInCall(null);
        setCallState('idle');
        setLocalStream(null);
        setRemoteStream(null);
        setCallCommandMode(false);
        stopCallCommandRecognizer();
        void resumeAssistantAndStart();
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
  }, [pauseAssistantListening, resumeAssistantAndStart, setCallCommandMode, startCallCommandRecognizer, stopCallCommandRecognizer]);

  const acceptCall  = async () => {
    if (!callRef.current || !incomingRef.current) {
      await speakViaTts('现在没有来电。');
      return;
    }
    await pauseAssistantListening();
    await setCallCommandMode(true);
    callRef.current.accept();
    setCallState('active');
    startCallCommandRecognizer();
  };
  const declineCall = () => {
    if (callRef.current) callRef.current.reject();
    setIncoming(null);
    setInCall(null);
    setCallState('idle');
    setCallCommandMode(false);
    stopCallCommandRecognizer();
  };
  const endCall     = () => {
    if (callRef.current) callRef.current.hangup();
    setInCall(null);
    setIncoming(null);
    setCallState('idle');
    setCallCommandMode(false);
    stopCallCommandRecognizer();
  };
  endCallRef.current = endCall;
  const toggleMute   = (v) => callRef.current && callRef.current.toggleMute(v);
  const toggleCamera = (v) => callRef.current && callRef.current.toggleCamera(v);

  useEffect(() => {
    const onClientAction = async (e) => {
      const detail = e.detail || {};
      const action = detail.action;
      if (!action) return;
      if (action === 'robot_action') return;
      setAiState('idle');
      if (action === 'accept_call') {
        await acceptCall();
      } else if (action === 'reject_call') {
        if (incomingRef.current) {
          await pauseAssistantListening();
          declineCall();
          await speakAndWait('已经帮您拒接。');
          await resumeAssistantAndStart();
        } else {
          await pauseAssistantListening();
          await speakAndWait('现在没有来电。');
          await resumeAssistantAndStart();
        }
      } else if (action === 'hangup_call') {
        if (callRef.current) {
          endCall();
          await resumeAssistantAndStart();
        } else if (incomingRef.current) {
          await pauseAssistantListening();
          declineCall();
          await speakAndWait('已经挂掉来电。');
          await resumeAssistantAndStart();
        } else {
          await pauseAssistantListening();
          await speakAndWait('现在没有正在进行的通话。');
          await resumeAssistantAndStart();
        }
      } else if (action === 'read_family_messages') {
        await readFamilyMessages(detail.contact_name || detail.target_name || '');
      } else if (action === 'announce_unread') {
        await announceUnread();
      } else if (action === 'stop_playback') {
        await stopTtsPlayback();
        stopPlayback();
        await resumeAssistantAndStart();
      }
    };
    window.addEventListener('xz:client-action', onClientAction);
    return () => window.removeEventListener('xz:client-action', onClientAction);
  }, [announceUnread, pauseAssistantListening, readFamilyMessages, resumeAssistantAndStart, speakAndWait, stopPlayback, stopTtsPlayback]);

  return (
    <PaperBg>
      <TopBar
        connected={connected}
        recording={recording}
        unread={unread}
        micOk={micOk}
        connectStatus={connectStatus}
        onOpenSettings={() => setSettingsOpen(true)}
        dignityMode={dignityMode}
        onToggleDignityMode={toggleDignityMode}
      />
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
          <ChatScreen
            aiState={aiState}
            msg={msg}
            lastHeard={lastHeard}
            connected={connected}
            recording={recording}
            userSpeaking={userSpeaking}
            dignityMode={dignityMode}
            dignityStatus={dignityStatus}
          />
        </section>
        <section style={{ position: 'relative', minWidth: 0, overflow: 'hidden', background: 'rgba(255,250,242,0.28)' }}>
          {dignityMode ? (
            <DignityDebugPanel
              turns={dignityTurns}
              status={dignityStatus}
              openingReply={dignityOpeningReply}
              busy={dignityDebugBusy}
              documentBusy={dignityDocumentBusy}
              documentConfirmBusy={dignityDocumentConfirmBusy}
              document={dignityDocument}
              documentUrl={dignityDocumentUrl}
              voiceMode={dignityVoiceMode}
              recording={recording}
              onRunTurn={runDignityDebugTurn}
              onReset={resetDignityDebug}
              onGenerateDocument={generateDignityDocument}
              onConfirmDocument={confirmDignityDocument}
              onDocumentChange={setDignityDocument}
              onToggleVoiceMode={toggleDignityVoiceMode}
            />
          ) : (
            <InboxScreen contacts={contacts} refreshContacts={loadContacts} eventTick={eventTick} maxUploadMb={maxUploadMb} onOpenContact={markThreadRead} />
          )}
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
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </PaperBg>
  );
}
