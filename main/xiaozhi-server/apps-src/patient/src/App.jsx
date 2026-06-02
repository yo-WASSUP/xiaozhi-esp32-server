import { useCallback, useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from './constants';
import PaperBg from './components/PaperBg';
import TopBar from './components/TopBar';
import ConnectBar from './components/ConnectBar';
import ChatScreen from './screens/ChatScreen';
import InboxScreen from './screens/InboxScreen';
import DignityDebugPanel from './screens/DignityDebugPanel';
import DignityTherapyPanel from './screens/DignityTherapyPanel';
import IncomingCallOverlay from './components/IncomingCallOverlay';
import ActiveCallOverlay from './components/ActiveCallOverlay';
import SettingsPanel from './components/SettingsPanel';
import useFamilyMessageReader from './hooks/useFamilyMessageReader';

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
  const [patientWakeup, setPatientWakeup] = useState({ enabled: false, mode: 'sherpa_onnx_kws' });
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
  const [ordinaryVoiceAwake, setOrdinaryVoiceAwake] = useState(true);

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
  const ordinaryVoiceAwakeRef = useRef(false);
  const dignityLiveTurnStartedAtRef = useRef(null);
  const dignityDebugTurnStartedAtRef = useRef(null);
  const patientWakeupRef = useRef({ enabled: false, mode: 'sherpa_onnx_kws' });
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
  useEffect(() => { ordinaryVoiceAwakeRef.current = ordinaryVoiceAwake; }, [ordinaryVoiceAwake]);
  useEffect(() => { patientWakeupRef.current = patientWakeup; }, [patientWakeup]);

  // 拉一次配置（上传上限等）
  useEffect(() => {
    fetch('/api/hospice/config')
      .then(r => r.json())
      .then(j => {
        if (j && j.upload_max_mb) setMaxUploadMb(j.upload_max_mb);
        if (j && j.patient_wakeup) {
          setPatientWakeup(j.patient_wakeup);
          const wakeupEnabled = j.patient_wakeup.enabled === true
            && String(j.patient_wakeup.mode || '').toLowerCase() === 'sherpa_onnx_kws';
          setOrdinaryVoiceAwake(!wakeupEnabled);
          ordinaryVoiceAwakeRef.current = !wakeupEnabled;
        }
      })
      .catch(() => { });
  }, []);

  const unread = contacts.reduce((s, c) => s + (c.unread || 0), 0);
  const dignityDebugEnabled = new URLSearchParams(window.location.search).get('dignity_debug') === '1';
  const kwsWakeupEnabled = patientWakeup?.enabled === true && String(patientWakeup?.mode || '').toLowerCase() === 'sherpa_onnx_kws';

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

  const markThreadRead = useCallback(async (contactName, familyId = '') => {
    if (!contactName && !familyId) return;
    try {
      const params = new URLSearchParams({ device_id: DEVICE_ID });
      if (familyId) params.set('family_id', familyId);
      else params.set('contact_name', contactName);
      await fetch(`/api/hospice/thread/read?${params.toString()}`, { method: 'POST' });
      await loadContacts();
      setEventTick(t => t + 1);
    } catch (e) { console.error('标记已读失败', e); }
  }, [loadContacts]);

  const unbindFamily = useCallback(async (familyId) => {
    if (!familyId) return false;
    try {
      const params = new URLSearchParams({ device_id: DEVICE_ID, family_id: familyId });
      const r = await fetch(`/api/hospice/pairing/bindings?${params.toString()}`, { method: 'DELETE' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '解绑失败');
      await loadContacts();
      setEventTick(t => t + 1);
      return true;
    } catch (e) {
      console.error('解绑家属失败', e);
      setConnectStatus(e.message || '解绑家属失败');
      return false;
    }
  }, [loadContacts]);

  const stopTtsPlayback = useCallback(async () => {
    ttsPlaybackAbortRef.current = true;
    try {
      await fetch('/api/hospice/tts/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID }),
      });
    } catch (e) {
      console.error('停止TTS失败', e);
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
      console.error('TTS播报失败', e);
      return false;
    }
  }, []);

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

  const stopNormalRecording = useCallback(async () => {
    if (recordingRef.current && window.XiaozhiClient) {
      try { await window.XiaozhiClient.stopRecording(); } catch (_) { }
      recordingRef.current = false;
      setRecording(false);
    }
    userSpeakingRef.current = false;
    setUserSpeaking(false);
    setAiState('idle');
  }, []);

  const startWakeWordListening = useCallback(async () => {
    if (!window.XiaozhiClient || typeof window.XiaozhiClient.startWakeWord !== 'function') return false;
    try {
      return await window.XiaozhiClient.startWakeWord();
    } catch (e) {
      console.error('唤醒词监听启动失败', e);
      return false;
    }
  }, []);

  const stopWakeWordListening = useCallback(async () => {
    if (!window.XiaozhiClient || typeof window.XiaozhiClient.stopWakeWord !== 'function') return false;
    try {
      return await window.XiaozhiClient.stopWakeWord();
    } catch (_) {
      return false;
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
      console.error('自动拾音失败', err);
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
      setConnectStatus('请先连接小暖，再切换尊严疗法模式');
      return;
    }
    const nextAction = dignityMode ? 'stop' : 'start';
    const ok = await sendDignityAction(nextAction, { patient_id: DEVICE_ID });
    if (!ok) setConnectStatus('尊严疗法模式切换失败，请稍后再试');
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


  const normalizeCommandText = (text) => String(text || '').replace(/[\s,，。.!！?？、：:；;]/g, '');

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

  const updateDignityDocument = useCallback((nextDocument) => {
    setDignityDocument(nextDocument);
  }, []);

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

  const { announceUnread, readFamilyMessages, speakAndWait, stopPlayback } = useFamilyMessageReader({
    loadContacts,
    markThreadRead,
    pauseAssistantListening,
    resumeAssistantAndStart,
    speakViaTts,
    ttsPlaybackAbortRef,
  });

  // 联系人列表 + SSE 订阅
  useEffect(() => {
    loadContacts();
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    const bump = () => { loadContacts(); setEventTick(t => t + 1); };
    es.addEventListener('message.new', bump);
    es.addEventListener('message.read', bump);
    es.onerror = () => { /* 浏览器自动重试 */ };
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
    const onWakeWordDetected = async (e) => {
      if (!connectedRef.current || !micOkRef.current || dignityModeRef.current || inCallRef.current) return;
      setOrdinaryVoiceAwake(true);
      ordinaryVoiceAwakeRef.current = true;
      setConnectStatus('');
      setMsg('我在呢，您说。');
      await speakViaTts('我在呢，您说。');
      await stopWakeWordListening();
      await startListening();
      window.dispatchEvent(new CustomEvent('xz:client-action', {
        detail: {
          type: 'client_action',
          action: 'patient_voice_wakeup',
          text: e.detail?.label || 'wakeword',
          source: 'kws',
        },
      }));
    };
    const onWakeWordState = (e) => {
      if (e.detail?.state === 'error') {
        setConnectStatus(e.detail?.message || '本地唤醒词模型未就绪');
      }
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
        setDignityDocument(data.document || '');
        setDignityDocumentUrl(data.document_url || '');
        setDignityDocumentConfirmBusy(false);
        if (data.reply) setMsg(data.reply);
        void pauseAssistantListening();
      } else if (event === 'mode_stopped') {
        setDignityMode(false);
        setDignityVoiceMode(false);
        setDignityStatus(data);
        if (kwsWakeupEnabled) {
          setOrdinaryVoiceAwake(false);
          ordinaryVoiceAwakeRef.current = false;
          setUserSpeaking(false);
          userSpeakingRef.current = false;
          resumeAssistantListening();
          void stopNormalRecording();
        } else {
          void resumeAssistantAndStart();
        }
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
        setConnectStatus(data.message || '生命访谈文档生成失败');
      } else if (event === 'error') {
        dignityLiveTurnStartedAtRef.current = null;
        dignityDebugTurnStartedAtRef.current = null;
        setDignityDebugBusy(false);
        setDignityDocumentBusy(false);
        setDignityDocumentConfirmBusy(false);
        setConnectStatus(data.message || '尊严疗法模式处理失败');
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
        console.error('XiaozhiClient init 失败', err);
        setConnectStatus('连接模块初始化失败：' + (err?.message || '未知错误'));
      }
    };
    window.addEventListener('xz:connection', onConn);
    window.addEventListener('xz:state', onState);
    window.addEventListener('xz:llm', onLlm);
    window.addEventListener('xz:stt', onStt);
    window.addEventListener('xz:voice-activity', onVoiceActivity);
    window.addEventListener('xz:wakeword-detected', onWakeWordDetected);
    window.addEventListener('xz:wakeword-state', onWakeWordState);
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
      window.removeEventListener('xz:wakeword-detected', onWakeWordDetected);
      window.removeEventListener('xz:wakeword-state', onWakeWordState);
      window.removeEventListener('xz:error', onErr);
      window.removeEventListener('xz:dignity', onDignity);
      window.removeEventListener('xz:ready', onReady);
    };
  }, [connectXiaozhi, kwsWakeupEnabled, pauseAssistantListening, resumeAssistantAndStart, resumeAssistantListening, scheduleReconnect, speakViaTts, startListening, stopNormalRecording, stopTtsPlayback, stopWakeWordListening]);

  useEffect(() => {
    if (!connected || !micOk || assistantHold || inCall) return;
    if (dignityMode) {
      if (dignityVoiceMode) startListening();
      return;
    }
    if (kwsWakeupEnabled && !ordinaryVoiceAwake) {
      stopNormalRecording();
      startWakeWordListening();
      return;
    }
    startListening();
  }, [assistantHold, connected, dignityMode, dignityVoiceMode, inCall, kwsWakeupEnabled, micOk, ordinaryVoiceAwake, startListening, startWakeWordListening, stopNormalRecording]);

  useEffect(() => {
    if (!kwsWakeupEnabled) {
      setOrdinaryVoiceAwake(true);
      ordinaryVoiceAwakeRef.current = true;
      stopWakeWordListening();
      return;
    }
    if (!window.XiaozhiClient || typeof window.XiaozhiClient.initWakeWord !== 'function') return;
    window.XiaozhiClient.initWakeWord(patientWakeup).catch((e) => {
      console.error('唤醒词模型初始化失败', e);
      setConnectStatus('本地唤醒词模型初始化失败：' + (e?.message || '未知错误'));
    });
  }, [kwsWakeupEnabled, patientWakeup, stopWakeWordListening]);

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
    if (window.XiaozhiClient && typeof window.XiaozhiClient.releaseWakeWord === 'function') {
      window.XiaozhiClient.releaseWakeWord();
    }
  }, [stopCallCommandRecognizer, stopPlayback]);

  // 通话（WebRTC）
  const callRef = useRef(null);
  const [localStream, setLocalStream]   = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);

  useEffect(() => {
    const client = new window.CallClient({
      deviceId: DEVICE_ID,
      role: 'patient',
      onIncoming: ({ fromName, callType }) => {
        setIncoming({
          caller: { from: fromName || '家人', avatar: '家' },
          callType,
        });
        setCallState('incoming');
        resumeAssistantAndStart();
      },
      onLocalStream:  (s) => setLocalStream(s),
      onRemoteStream: (s) => setRemoteStream(s),
      onState: (s) => {
        // 状态为 connecting / active 时，把来电浮层切换为通话浮层
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
      } else if (action === 'patient_voice_wakeup') {
        setOrdinaryVoiceAwake(true);
        ordinaryVoiceAwakeRef.current = true;
        setConnectStatus('');
        if (detail.source === 'kws') return;
        if (detail.reply) {
          setMsg(detail.reply);
          await speakViaTts(detail.reply);
        }
      } else if (action === 'patient_voice_sleep') {
        if (!kwsWakeupEnabled) return;
        setOrdinaryVoiceAwake(false);
        ordinaryVoiceAwakeRef.current = false;
        setAiState('idle');
        setMsg(null);
        setLastHeard('');
        setUserSpeaking(false);
        userSpeakingRef.current = false;
        await stopTtsPlayback();
        stopPlayback();
        if (kwsWakeupEnabled && !dignityModeRef.current && !inCallRef.current) {
          await stopNormalRecording();
          await startWakeWordListening();
        }
      }
    };
    window.addEventListener('xz:client-action', onClientAction);
    return () => window.removeEventListener('xz:client-action', onClientAction);
  }, [announceUnread, kwsWakeupEnabled, pauseAssistantListening, readFamilyMessages, resumeAssistantAndStart, speakAndWait, speakViaTts, startWakeWordListening, stopNormalRecording, stopPlayback, stopTtsPlayback]);

  return (
    <PaperBg>
      <TopBar
        connected={connected}
        recording={recording}
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
            ordinaryVoiceAwake={ordinaryVoiceAwake || !kwsWakeupEnabled}
          />
        </section>
        <section style={{ position: 'relative', minWidth: 0, overflow: 'hidden', background: 'rgba(255,250,242,0.28)' }}>
          {dignityMode && dignityDebugEnabled ? (
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
              onDocumentChange={updateDignityDocument}
              onToggleVoiceMode={toggleDignityVoiceMode}
            />
          ) : dignityMode ? (
            <DignityTherapyPanel
              status={dignityStatus}
              openingReply={dignityOpeningReply}
              documentBusy={dignityDocumentBusy}
              documentConfirmBusy={dignityDocumentConfirmBusy}
              document={dignityDocument}
              documentUrl={dignityDocumentUrl}
              voiceMode={dignityVoiceMode}
              recording={recording}
              onReset={resetDignityDebug}
              onGenerateDocument={generateDignityDocument}
              onConfirmDocument={confirmDignityDocument}
              onDocumentChange={updateDignityDocument}
              onToggleVoiceMode={toggleDignityVoiceMode}
            />
          ) : (
            <InboxScreen contacts={contacts} refreshContacts={loadContacts} eventTick={eventTick} maxUploadMb={maxUploadMb} onOpenContact={markThreadRead} onUnbindContact={unbindFamily} />
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
