import { useCallback, useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from './constants';
import PaperBg from './components/PaperBg';
import TopBar from './components/TopBar';
import ConnectBar from './components/ConnectBar';
import HomeScreen, { APP_TITLES } from './screens/HomeScreen';
import ComingSoonScreen from './screens/ComingSoonScreen';
import ChatScreen from './screens/ChatScreen';
import InboxScreen from './screens/InboxScreen';
import DignityDebugPanel from './screens/DignityDebugPanel';
import DignityTherapyPanel from './screens/DignityTherapyPanel';
import LegacyVideoScreen from './screens/LegacyVideoScreen';
import IncomingCallOverlay from './components/IncomingCallOverlay';
import ActiveCallOverlay from './components/ActiveCallOverlay';
import SettingsPanel from './components/SettingsPanel';
import InterviewAudioEditor from './components/InterviewAudioEditor';
import useFamilyMessageReader from './hooks/useFamilyMessageReader';
import { C } from './theme';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
const DIGNITY_SILENCE_DELAYS_MS = [45000, 60000, 60000];

function cleanReadableText(value) {
  return String(value || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/^[\s>*+-]+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/[>#*_~|[\]{}]/g, '')
    .replace(/-{3,}/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function readableJoin(parts) {
  return parts.map(cleanReadableText).filter(Boolean).join('。');
}

function buildLegacyCardReadingText(card) {
  if (!card) return '';
  const parts = [
    '我来为您读这张传承卡片。请您慢慢听，里面记录的是值得被记住的人生片段',
    card.title,
    card.subtitle,
    card.intro,
  ];
  for (const section of card.sections || []) {
    if (!section) continue;
    parts.push(section.title);
    parts.push(section.body);
    if (section.quote) parts.push(`这一段里，有一句很重要的话：${section.quote}`);
  }
  if (card.wish) parts.push(`还有一个心愿：${card.wish}`);
  if (card.closing) parts.push(card.closing);
  parts.push('这张卡片就读到这里。谢谢您愿意把这些珍贵的记忆留下来');
  return readableJoin(parts);
}

function buildFamilyLetterReadingText(letter) {
  if (!letter) return '';
  return readableJoin([
    '我来为您读这封写给家人的信。您可以安心听，也可以随时让我停下来',
    letter.title,
    letter.subtitle,
    letter.salutation,
    ...(letter.paragraphs || []),
    letter.signature,
    letter.date,
    '这封信读完了。愿这些话，能好好地陪伴您和家人',
  ]);
}

function buildDignityReadingText(kind, payload) {
  if (kind === 'document') {
    const document = cleanReadableText(payload);
    if (!document) return '';
    return readableJoin([
      '我来为您读这份人生故事。这里面整理了您刚才说过的重要经历和心里话。我们慢慢听',
      document,
      '人生故事读完了。这里的每一段经历，都值得被认真记住',
    ]);
  }
  if (kind === 'card') return buildLegacyCardReadingText(payload);
  if (kind === 'letter') return buildFamilyLetterReadingText(payload);
  return '';
}

function interviewSegmentId(text, index = 0) {
  let hash = 0;
  const value = String(text || '');
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(i)) | 0;
  }
  return `seg_${String(index + 1).padStart(3, '0')}_${Math.abs(hash).toString(36)}`;
}

function normalizeInterviewSegments(segments) {
  if (!Array.isArray(segments)) return [];
  return segments
    .map((item, index) => {
      const text = String(item?.text || item?.patient || item?.patient_text || '').trim();
      if (!text) return null;
      return {
        id: String(item?.id || interviewSegmentId(text, index)),
        text,
        speaker: item?.speaker || 'patient',
        deleted: !!item?.deleted,
        audio_url: item?.audio_url || '',
        start_time: Number.isFinite(Number(item?.start_time)) ? Number(item.start_time) : undefined,
        end_time: Number.isFinite(Number(item?.end_time)) ? Number(item.end_time) : undefined,
      };
    })
    .filter(Boolean);
}

function segmentsFromTranscript(transcript) {
  if (!Array.isArray(transcript)) return [];
  return normalizeInterviewSegments(transcript.map((turn, index) => ({
    id: turn?.id,
    text: turn?.patient || turn?.patient_text || turn?.text,
    speaker: turn?.speaker || 'patient',
    audio_url: turn?.audio_url,
    start_time: turn?.start_time,
    end_time: turn?.end_time,
    deleted: !!turn?.deleted,
    index,
  })));
}

function mergeInterviewSegments(current, incoming) {
  const currentList = normalizeInterviewSegments(current);
  const incomingList = normalizeInterviewSegments(incoming);
  const byId = new Map(currentList.map(item => [item.id, item]));
  for (const item of incomingList) {
    const old = byId.get(item.id);
    byId.set(item.id, old ? { ...item, deleted: old.deleted } : item);
  }
  return Array.from(byId.values());
}

function mergeAssistantDisplayText(current, incoming) {
  const previous = String(current || '').trim();
  const next = String(incoming || '').trim();
  if (!previous) return next;
  if (!next || previous.includes(next)) return previous;
  if (next.startsWith(previous)) return next;
  const maxOverlap = Math.min(previous.length, next.length);
  for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
    if (previous.slice(-overlap) === next.slice(0, overlap)) {
      return previous + next.slice(overlap);
    }
  }
  return previous + next;
}

export default function App() {
  const [activeApp, setActiveApp] = useState('home');
  const [aiState, setAiState]     = useState('idle');
  const [ordinaryMsg, setOrdinaryMsg] = useState(null);
  const [ordinaryLastHeard, setOrdinaryLastHeard] = useState('');
  const [dignityMsg, setDignityMsg] = useState(null);
  const [dignityLastHeard, setDignityLastHeard] = useState('');
  const [audioLevels, setAudioLevels] = useState({ input: 0, output: 0 });
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
  const [voiceMode, setVoiceMode] = useState(
    () => localStorage.getItem('xiaonuan_voice_mode') || 'doubao_s2s'
  );
  const [dignityMode, setDignityMode] = useState(false);
  const [dignityStatus, setDignityStatus] = useState(null);
  const [dignityOpeningReply, setDignityOpeningReply] = useState('');
  const [dignityTurns, setDignityTurns] = useState([]);
  const [dignityDebugBusy, setDignityDebugBusy] = useState(false);
  const [dignityDocumentBusy, setDignityDocumentBusy] = useState(false);
  const [dignityDocumentConfirmBusy, setDignityDocumentConfirmBusy] = useState(false);
  const [dignityMemoryBusy, setDignityMemoryBusy] = useState(false);
  const [dignityDocument, setDignityDocument] = useState('');
  const [dignityDocumentUrl, setDignityDocumentUrl] = useState('');
  const [legacyCardBusy, setLegacyCardBusy] = useState(false);
  const [legacyCard, setLegacyCard] = useState(null);
  const [legacyCardImageUrl, setLegacyCardImageUrl] = useState('');
  const [familyLetterBusy, setFamilyLetterBusy] = useState(false);
  const [familyLetter, setFamilyLetter] = useState(null);
  const [familyLetterImageUrl, setFamilyLetterImageUrl] = useState('');
  const [familyLetterTemplate, setFamilyLetterTemplate] = useState('warm');
  const [interviewSegments, setInterviewSegments] = useState([]);
  const [interviewAudioBusy, setInterviewAudioBusy] = useState(false);
  const [dignityVoiceMode, setDignityVoiceMode] = useState(false);
  const [dignityPaused, setDignityPaused] = useState(false);
  const [dignitySilencePromptCount, setDignitySilencePromptCount] = useState(0);
  const [ordinaryVoiceAwake, setOrdinaryVoiceAwake] = useState(true);
  const [dignityReadingKind, setDignityReadingKind] = useState('');
  const [assistantToolsOpen, setAssistantToolsOpen] = useState(false);
  const [assistantToolView, setAssistantToolView] = useState('audio');
  const [robotActionLog, setRobotActionLog] = useState([]);

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
  const activeAppRef = useRef('home');
  const ordinaryVoiceAwakeRef = useRef(false);
  const dignityLiveTurnStartedAtRef = useRef(null);
  const dignityDebugTurnStartedAtRef = useRef(null);
  const patientWakeupRef = useRef({ enabled: false, mode: 'sherpa_onnx_kws' });
  const ttsPlaybackAbortRef = useRef(false);
  const speakingFallbackTimerRef = useRef(null);
  const dignityOpeningSpokenRef = useRef(false);
  const dignitySilenceTimerRef = useRef(null);
  const assistantReplyRef = useRef({ sentenceId: '', text: '', final: false });

  useEffect(() => { connectedRef.current = connected; }, [connected]);
  useEffect(() => { userSpeakingRef.current = userSpeaking; }, [userSpeaking]);
  useEffect(() => { micOkRef.current = micOk; }, [micOk]);
  useEffect(() => { assistantHoldRef.current = assistantHold; }, [assistantHold]);
  useEffect(() => { inCallRef.current = inCall; }, [inCall]);
  useEffect(() => { incomingRef.current = incoming; }, [incoming]);
  useEffect(() => { callStateRef.current = callState; }, [callState]);
  useEffect(() => { dignityModeRef.current = dignityMode; }, [dignityMode]);
  useEffect(() => { activeAppRef.current = activeApp; }, [activeApp]);
  useEffect(() => { ordinaryVoiceAwakeRef.current = ordinaryVoiceAwake; }, [ordinaryVoiceAwake]);
  useEffect(() => { patientWakeupRef.current = patientWakeup; }, [patientWakeup]);

  // 拉一次配置（上传上限等）
  useEffect(() => {
    fetch('/api/hospice/config')
      .then(r => r.json())
      .then(j => {
        if (j && j.upload_max_mb) setMaxUploadMb(j.upload_max_mb);
        if (j && j.patient_wakeup) {
          const wakeup = {
            ...j.patient_wakeup,
            enabled: j.enable_patient_wakeup === false ? false : j.patient_wakeup.enabled === true,
          };
          setPatientWakeup(wakeup);
          const wakeupEnabled = wakeup.enabled === true
            && String(wakeup.mode || '').toLowerCase() === 'sherpa_onnx_kws';
          setOrdinaryVoiceAwake(!wakeupEnabled);
          ordinaryVoiceAwakeRef.current = !wakeupEnabled;
        }
      })
      .catch(() => { });
  }, []);

  const unread = contacts.reduce((s, c) => s + (c.unread || 0), 0);
  const dignityDebugEnabled = new URLSearchParams(window.location.search).get('dignity_debug') === '1';
  const robotDebugEnabled = new URLSearchParams(window.location.search).get('robot_debug') === '1';
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

  const speakViaTtsAndWait = useCallback(async (text) => {
    const content = (text || '').trim();
    if (!content) return false;

    let accepted = false;
    let sawSpeaking = false;
    let finish = () => {};
    const completion = new Promise(resolve => {
      const timeoutMs = Math.min(20000, Math.max(5000, content.length * 280 + 2500));
      const onState = event => {
        const state = event.detail?.state;
        if (state === 'speaking') sawSpeaking = true;
        if (state === 'idle' && (accepted || sawSpeaking)) finish();
      };
      const timer = window.setTimeout(() => finish(), timeoutMs);
      finish = () => {
        window.clearTimeout(timer);
        window.removeEventListener('xz:state', onState);
        resolve();
      };
      window.addEventListener('xz:state', onState);
    });

    accepted = await speakViaTts(content);
    if (!accepted) {
      finish();
      return false;
    }
    await completion;
    return true;
  }, [speakViaTts]);

  const pauseAssistantListening = useCallback(async () => {
    setAssistantHold(true);
    assistantHoldRef.current = true;
    if (recordingRef.current && window.XiaozhiClient) {
      recordingRef.current = false;
      setRecording(false);
      try { await window.XiaozhiClient.stopRecording(); } catch (_) { }
      userSpeakingRef.current = false;
      setUserSpeaking(false);
      setAiState('idle');
    }
  }, []);

  const stopNormalRecording = useCallback(async () => {
    if (recordingRef.current && window.XiaozhiClient) {
      recordingRef.current = false;
      setRecording(false);
      try { await window.XiaozhiClient.stopRecording(); } catch (_) { }
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
    const assistantPageActive = activeAppRef.current === 'voice' || activeAppRef.current === 'dignity';
    if (!allowInCall && !incomingRef.current && !assistantPageActive) {
      await pauseAssistantListening();
      return;
    }
    resumeAssistantListening();
    await sleep(delay);
    await startListening({ allowInCall });
  }, [pauseAssistantListening, resumeAssistantListening, startListening]);

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

  const openPatientApp = useCallback(async (appId) => {
    activeAppRef.current = appId;
    setActiveApp(appId);

    if (appId === 'voice') {
      if (dignityModeRef.current) {
        await sendDignityAction('stop', { patient_id: DEVICE_ID });
      }
      resumeAssistantListening();
      return;
    }

    if (appId === 'dignity') {
      if (!connectedRef.current) {
        setConnectStatus('请先连接小暖，再开始尊严疗法');
        return;
      }
      if (!dignityModeRef.current) {
        const ok = await sendDignityAction('start', { patient_id: DEVICE_ID });
        if (!ok) setConnectStatus('尊严疗法启动失败，请稍后再试');
      }
      return;
    }

    await pauseAssistantListening();
    await stopWakeWordListening();
  }, [pauseAssistantListening, resumeAssistantListening, sendDignityAction, stopWakeWordListening]);

  const returnToHome = useCallback(async () => {
    try {
      await window.XiaozhiClient?.interrupt?.('leave_voice_page');
    } catch (e) {
      console.error('退出语音页面时停止播放失败', e);
    }
    activeAppRef.current = 'home';
    setActiveApp('home');
    void stopTtsPlayback();
    await pauseAssistantListening();
    await stopWakeWordListening();
    if (dignityModeRef.current) {
      const ok = await sendDignityAction('stop', { patient_id: DEVICE_ID });
      if (!ok) setConnectStatus('尊严疗法退出失败，请稍后再试');
    }
  }, [pauseAssistantListening, sendDignityAction, stopTtsPlayback, stopWakeWordListening]);

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
    setDignityReadingKind('');
    setLegacyCard(null);
    setLegacyCardImageUrl('');
    setLegacyCardBusy(false);
    setFamilyLetter(null);
    setFamilyLetterImageUrl('');
    setFamilyLetterBusy(false);
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
      setConnectStatus('人生故事生成请求发送失败');
    }
  }, [sendDignityAction]);

  const confirmDignityDocument = useCallback(async (documentText) => {
    const document = String(documentText || '').trim();
    if (!document) {
      setConnectStatus('请先生成并确认人生故事内容');
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

  const saveDignityMemory = useCallback(async (memory) => {
    setDignityMemoryBusy(true);
    const ok = await sendDignityAction('update_memory', {
      patient_id: DEVICE_ID,
      memory,
    });
    if (!ok) {
      setDignityMemoryBusy(false);
      setConnectStatus('生命记忆保存请求发送失败');
    }
    return ok;
  }, [sendDignityAction]);

  const loadDignityArtifacts = useCallback(async () => {
    try {
      const [cardRes, letterRes, audioRes] = await Promise.all([
        fetch(`/api/hospice/legacy-card/latest?device_id=${encodeURIComponent(DEVICE_ID)}`),
        fetch(`/api/hospice/family-letter/latest?device_id=${encodeURIComponent(DEVICE_ID)}`),
        fetch(`/api/hospice/interview/audio-segments/latest?device_id=${encodeURIComponent(DEVICE_ID)}`),
      ]);
      const cardJson = await cardRes.json().catch(() => ({}));
      const letterJson = await letterRes.json().catch(() => ({}));
      const audioJson = await audioRes.json().catch(() => ({}));
      if (cardRes.ok && cardJson.success && cardJson.card) {
        setLegacyCard(cardJson.card);
        setLegacyCardImageUrl(cardJson.image_url || '');
      }
      if (letterRes.ok && letterJson.success && letterJson.letter) {
        setFamilyLetter(letterJson.letter);
        setFamilyLetterImageUrl(letterJson.image_url || '');
        if (letterJson.template) setFamilyLetterTemplate(letterJson.template);
      }
      if (audioRes.ok && audioJson.success) {
        setInterviewSegments(items => mergeInterviewSegments(audioJson.segments || [], items));
      }
    } catch (err) {
      console.error('load dignity artifacts failed', err);
    }
  }, []);

  const updateLegacyCard = useCallback((nextCard) => {
    setLegacyCard(nextCard);
  }, []);

  const updateFamilyLetter = useCallback((nextLetter) => {
    setFamilyLetter(nextLetter);
  }, []);

  const generateLegacyCard = useCallback(async () => {
    const memory = dignityStatus?.dignity_memory || {};
    const hasMemory = Object.values(memory).some(items => Array.isArray(items) && items.length);
    if (!hasMemory) {
      setConnectStatus('还没有可生成传承故事卡片的访谈记忆');
      return;
    }
    setLegacyCardBusy(true);
    setLegacyCardImageUrl('');
    try {
      const r = await fetch('/api/hospice/legacy-card/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, memory }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '传承故事卡片生成失败');
      setLegacyCard(j.card || null);
      setLegacyCardImageUrl(j.image_url || '');
      setConnectStatus('');
    } catch (err) {
      console.error('legacy card generation failed', err);
      setConnectStatus(err?.message || '传承故事卡片生成失败');
    } finally {
      setLegacyCardBusy(false);
    }
  }, [dignityStatus]);

  const saveLegacyCard = useCallback(async (cardDraft = legacyCard) => {
    if (!cardDraft) {
      setConnectStatus('还没有可保存的传承卡片内容');
      return;
    }
    setLegacyCardBusy(true);
    try {
      const r = await fetch('/api/hospice/legacy-card/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, card: cardDraft }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '传承卡片保存失败');
      setLegacyCard(j.card || cardDraft);
      setLegacyCardImageUrl(j.image_url || '');
      setConnectStatus('');
    } catch (err) {
      console.error('legacy card save failed', err);
      setConnectStatus(err?.message || '传承卡片保存失败');
    } finally {
      setLegacyCardBusy(false);
    }
  }, [legacyCard]);

  const generateFamilyLetter = useCallback(async () => {
    const memory = dignityStatus?.dignity_memory || {};
    const hasMemory = Object.values(memory).some(items => Array.isArray(items) && items.length);
    if (!hasMemory) {
      setConnectStatus('还没有可生成家信的访谈记忆');
      return;
    }
    setFamilyLetterBusy(true);
    setFamilyLetterImageUrl('');
    try {
      const r = await fetch('/api/hospice/family-letter/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, memory, template: familyLetterTemplate }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '家信生成失败');
      setFamilyLetter(j.letter || null);
      setFamilyLetterImageUrl(j.image_url || '');
      if (j.template) setFamilyLetterTemplate(j.template);
      setConnectStatus('');
    } catch (err) {
      console.error('family letter generation failed', err);
      setConnectStatus(err?.message || '家信生成失败');
    } finally {
      setFamilyLetterBusy(false);
    }
  }, [dignityStatus, familyLetterTemplate]);

  const saveFamilyLetter = useCallback(async (letterDraft = familyLetter) => {
    if (!letterDraft) {
      setConnectStatus('还没有可保存的家信内容');
      return;
    }
    setFamilyLetterBusy(true);
    try {
      const r = await fetch('/api/hospice/family-letter/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, letter: letterDraft, template: familyLetterTemplate }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '家信保存失败');
      setFamilyLetter(j.letter || letterDraft);
      setFamilyLetterImageUrl(j.image_url || '');
      if (j.template) setFamilyLetterTemplate(j.template);
      setConnectStatus('');
    } catch (err) {
      console.error('family letter save failed', err);
      setConnectStatus(err?.message || '家信保存失败');
    } finally {
      setFamilyLetterBusy(false);
    }
  }, [familyLetter, familyLetterTemplate]);

  const toggleInterviewSegmentDeleted = useCallback((segmentId) => {
    setInterviewSegments(items => items.map(item => (
      item.id === segmentId ? { ...item, deleted: !item.deleted } : item
    )));
  }, []);

  const saveInterviewAudioSegments = useCallback(async (segments = interviewSegments) => {
    const payloadSegments = normalizeInterviewSegments(segments);
    setInterviewAudioBusy(true);
    try {
      const r = await fetch('/api/hospice/interview/audio-segments/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, segments: payloadSegments }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '访谈语音编辑保存失败');
      setInterviewSegments(normalizeInterviewSegments(j.segments || payloadSegments));
      setConnectStatus('');
    } catch (err) {
      console.error('interview audio edit save failed', err);
      setConnectStatus(err?.message || '访谈语音编辑保存失败');
    } finally {
      setInterviewAudioBusy(false);
    }
  }, [interviewSegments]);

  const toggleDignityVoiceMode = useCallback(async () => {
    if (!dignityMode) return;
    if (dignityPaused) {
      const ok = await sendDignityAction('resume', { patient_id: DEVICE_ID, source: 'patient_button' });
      if (!ok) setConnectStatus('继续访谈失败，请稍后再试');
      return;
    }
    if (dignityVoiceMode) {
      try {
        await window.XiaozhiClient?.interrupt?.('dignity_pause');
      } catch (_) { }
      await stopTtsPlayback();
      const ok = await sendDignityAction('pause', {
        patient_id: DEVICE_ID,
        source: 'patient_button',
        reason: 'patient_request',
      });
      if (!ok) setConnectStatus('暂停访谈失败，请稍后再试');
      return;
    }
    if (!connectedRef.current || !micOkRef.current) {
      setConnectStatus('请先连接并允许麦克风权限，再开始语音访谈');
      return;
    }
    await pauseAssistantListening();
    if (!dignityOpeningSpokenRef.current) {
      const openingReply = (
        dignityOpeningReply
        || dignityStatus?.reply
        || '您好，我是小暖。今天我来陪您聊聊天。您现在感觉还好吗？'
      ).trim();
      if (openingReply) {
        assistantReplyRef.current = { sentenceId: '', text: openingReply, final: true };
        setDignityMsg(openingReply);
        setAiState('speaking');
        const spoken = await speakViaTtsAndWait(openingReply);
        dignityOpeningSpokenRef.current = spoken;
        if (!spoken) setConnectStatus('开场白播放失败，您可以直接开始说话');
      }
    }
    setDignityVoiceMode(true);
    await resumeAssistantAndStart();
  }, [dignityMode, dignityOpeningReply, dignityPaused, dignityStatus?.reply, dignityVoiceMode, pauseAssistantListening, resumeAssistantAndStart, sendDignityAction, speakViaTtsAndWait, stopTtsPlayback]);

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

  const handleVoiceModeChange = useCallback((nextMode) => {
    const normalized = nextMode === 'cascade' ? 'cascade' : 'doubao_s2s';
    setVoiceMode(normalized);
    localStorage.setItem('xiaonuan_voice_mode', normalized);
    window.XiaozhiClient?.setVoiceMode?.(normalized);
    setConnectStatus(normalized === 'doubao_s2s' ? '正在切换到端到端模式...' : '正在切换到标准模式...');
    if (connectedRef.current) {
      window.XiaozhiClient?.disconnect?.();
    } else {
      scheduleReconnect(100);
    }
  }, [scheduleReconnect]);

  const { announceUnread, readFamilyMessages, speakAndWait, stopPlayback } = useFamilyMessageReader({
    loadContacts,
    markThreadRead,
    pauseAssistantListening,
    resumeAssistantAndStart,
    speakViaTts,
    ttsPlaybackAbortRef,
  });

  const stopDignityReading = useCallback(async ({ resume = true } = {}) => {
    await stopTtsPlayback();
    stopPlayback();
    setDignityReadingKind('');
    if (resume && dignityModeRef.current && !dignityVoiceMode && !inCallRef.current) {
      await pauseAssistantListening();
    }
  }, [dignityVoiceMode, pauseAssistantListening, stopPlayback, stopTtsPlayback]);

  const readDignityContent = useCallback(async (kind, payload) => {
    const text = buildDignityReadingText(kind, payload);
    if (!text) {
      setConnectStatus('当前还没有可朗读的内容');
      return;
    }
    await stopDignityReading({ resume: false });
    await pauseAssistantListening();
    setDignityReadingKind(kind);
    const ok = await speakViaTts(text);
    if (!ok) {
      setDignityReadingKind('');
      setConnectStatus('朗读启动失败，请稍后再试');
    } else {
      setConnectStatus('');
    }
  }, [pauseAssistantListening, speakViaTts, stopDignityReading]);

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
      const detail = e.detail || {};
      const text = String(detail.text || '').trim();
      if (!text) return;
      const sentenceId = detail.sentenceId || '';
      const current = assistantReplyRef.current;
      if (sentenceId && current.sentenceId && sentenceId !== current.sentenceId) {
        assistantReplyRef.current = { sentenceId, text: '', final: false };
      }
      if (detail.final) {
        assistantReplyRef.current = { sentenceId, text, final: true };
      } else {
        if (assistantReplyRef.current.final) return;
        const merged = mergeAssistantDisplayText(assistantReplyRef.current.text, text);
        assistantReplyRef.current = { sentenceId, text: merged, final: false };
      }
      const displayText = assistantReplyRef.current.text;
      if (dignityModeRef.current) setDignityMsg(displayText);
      else setOrdinaryMsg(displayText);
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
      assistantReplyRef.current = { sentenceId: '', text: '', final: false };
      if (dignityModeRef.current) {
        setDignityLastHeard(e.detail?.text || '');
        setDignitySilencePromptCount(0);
      } else {
        setOrdinaryLastHeard(e.detail?.text || '');
      }
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
    const onAudioLevel = e => {
      const detail = e.detail || {};
      setAudioLevels({
        input: Number(detail.input) || 0,
        output: Number(detail.output) || 0,
      });
    };
    const onWakeWordDetected = async (e) => {
      if (!kwsWakeupEnabled || patientWakeupRef.current?.enabled !== true) return;
      if (!connectedRef.current || !micOkRef.current || dignityModeRef.current || inCallRef.current) return;
      setOrdinaryVoiceAwake(true);
      ordinaryVoiceAwakeRef.current = true;
      setConnectStatus('');
      setOrdinaryMsg('我在呢，您说。');
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
      if (!kwsWakeupEnabled || patientWakeupRef.current?.enabled !== true) {
        return;
      }
      if (e.detail?.state === 'error') {
        setConnectStatus(e.detail?.message || '本地唤醒词模型未就绪');
      }
    };
    const onErr = e => setConnectStatus(e.detail?.message || e.detail?.error?.message || '连接模块初始化失败');
    const onVoiceMode = e => {
      const detail = e.detail || {};
      if (detail.mode === 'cascade' && detail.requested_mode === 'doubao_s2s' && detail.reason) {
        setVoiceMode('cascade');
        localStorage.setItem('xiaonuan_voice_mode', 'cascade');
        window.XiaozhiClient?.setVoiceMode?.('cascade');
        setConnectStatus(`端到端连接失败，已切换标准模式：${detail.reason}`);
      } else if (detail.mode === 'doubao_s2s') {
        setConnectStatus('');
      }
    };
    const onRobotAction = e => {
      const detail = e.detail || {};
      setRobotActionLog(items => [
        {
          id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
          time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
          ...detail,
        },
        ...items,
      ].slice(0, 3));
    };
    const onDignity = e => {
      const detail = e.detail || {};
      const event = detail.event;
      const data = detail.data || {};
      if (event === 'mode_started') {
        const autoVoiceMode = data.auto_voice_mode === true || data.source === 'voice_command';
        dignityOpeningSpokenRef.current = false;
        dignityModeRef.current = true;
        activeAppRef.current = 'dignity';
        setActiveApp('dignity');
        setDignityMode(true);
        setDignityVoiceMode(autoVoiceMode);
        setDignityPaused(!!data.paused);
        setDignitySilencePromptCount(Number(data.silence_prompt_count) || 0);
        setDignityLastHeard('');
        setUserSpeaking(false);
        userSpeakingRef.current = false;
        setDignityStatus(data);
        setDignityOpeningReply(data.reply || '');
        setDignityDocument(data.document || '');
        setDignityDocumentUrl(data.document_url || '');
        setDignityDocumentConfirmBusy(false);
        if (data.reply) {
          assistantReplyRef.current = { sentenceId: '', text: data.reply, final: true };
          setDignityMsg(data.reply);
        }
        void loadDignityArtifacts();
        if (autoVoiceMode) {
          resumeAssistantListening();
        } else {
          void pauseAssistantListening();
        }
      } else if (event === 'mode_stopped') {
        dignityOpeningSpokenRef.current = false;
        dignityModeRef.current = false;
        assistantReplyRef.current = { sentenceId: '', text: '', final: false };
        setDignityMode(false);
        setDignityVoiceMode(false);
        setDignityPaused(false);
        setDignitySilencePromptCount(0);
        setDignityReadingKind('');
        setDignityStatus(data);
        if (activeAppRef.current !== 'voice') {
          void pauseAssistantListening();
          void stopWakeWordListening();
        } else if (kwsWakeupEnabled) {
          setOrdinaryVoiceAwake(false);
          ordinaryVoiceAwakeRef.current = false;
          setUserSpeaking(false);
          userSpeakingRef.current = false;
          resumeAssistantListening();
          void stopNormalRecording();
        } else {
          void resumeAssistantAndStart();
        }
      } else if (event === 'mode_paused') {
        setDignityPaused(true);
        setDignityStatus(data);
        setDignitySilencePromptCount(Number(data.silence_prompt_count) || 0);
        if (data.reply) {
          setAiState('speaking');
          assistantReplyRef.current = { sentenceId: '', text: data.reply, final: true };
          setDignityMsg(data.reply);
        }
      } else if (event === 'mode_resumed') {
        setDignityPaused(false);
        setDignityVoiceMode(true);
        setDignityStatus(data);
        setDignitySilencePromptCount(0);
        if (data.reply) {
          setAiState('speaking');
          assistantReplyRef.current = { sentenceId: '', text: data.reply, final: true };
          setDignityMsg(data.reply);
        }
        void resumeAssistantAndStart();
      } else if (event === 'silence_prompt') {
        setDignityStatus(data);
        setDignitySilencePromptCount(Number(data.silence_prompt_count) || 0);
        if (data.reply) {
          setAiState('speaking');
          assistantReplyRef.current = { sentenceId: '', text: data.reply, final: true };
          setDignityMsg(data.reply);
        }
      } else if (event === 'turn_result' || event === 'nurse_alert') {
        const nextData = attachClientLatency(data, dignityLiveTurnStartedAtRef);
        if (typeof nextData.paused === 'boolean') setDignityPaused(nextData.paused);
        setDignitySilencePromptCount(Number(nextData.silence_prompt_count) || 0);
        setDignityStatus(nextData);
        setDignityTurns(items => [...items, nextData]);
        if (nextData.reply) {
          assistantReplyRef.current = { sentenceId: '', text: nextData.reply, final: true };
          setDignityMsg(nextData.reply);
        }
      } else if (event === 'state_updated') {
        if (typeof data.paused === 'boolean') setDignityPaused(data.paused);
        setDignitySilencePromptCount(Number(data.silence_prompt_count) || 0);
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
        if (data.reply) {
          assistantReplyRef.current = { sentenceId: '', text: data.reply, final: true };
          setDignityMsg(data.reply);
        }
      } else if (event === 'document_started') {
        setDignityDocumentBusy(true);
        setDignityDocumentConfirmBusy(false);
      } else if (event === 'memory_update_started') {
        setDignityMemoryBusy(true);
      } else if (event === 'memory_updated') {
        setDignityMemoryBusy(false);
        setDignityStatus(prev => ({ ...(prev || {}), dignity_memory: data.dignity_memory || {} }));
        setConnectStatus('');
      } else if (event === 'memory_error') {
        setDignityMemoryBusy(false);
        setConnectStatus(data.message || '生命记忆保存失败');
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
        setConnectStatus(data.message || '人生故事生成失败');
      } else if (event === 'error') {
        dignityLiveTurnStartedAtRef.current = null;
        dignityDebugTurnStartedAtRef.current = null;
        setDignityDebugBusy(false);
        setDignityMemoryBusy(false);
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
    window.addEventListener('xz:audio-level', onAudioLevel);
    window.addEventListener('xz:wakeword-detected', onWakeWordDetected);
    window.addEventListener('xz:wakeword-state', onWakeWordState);
    window.addEventListener('xz:error', onErr);
    window.addEventListener('xz:voice-mode', onVoiceMode);
    window.addEventListener('xz:robot-action', onRobotAction);
    window.addEventListener('xz:dignity', onDignity);
    window.addEventListener('xz:ready', onReady);
    if (window.XiaozhiClient) onReady();
    return () => {
      window.removeEventListener('xz:connection', onConn);
      window.removeEventListener('xz:state', onState);
      window.removeEventListener('xz:llm', onLlm);
      window.removeEventListener('xz:stt', onStt);
      window.removeEventListener('xz:voice-activity', onVoiceActivity);
      window.removeEventListener('xz:audio-level', onAudioLevel);
      window.removeEventListener('xz:wakeword-detected', onWakeWordDetected);
      window.removeEventListener('xz:wakeword-state', onWakeWordState);
      window.removeEventListener('xz:error', onErr);
      window.removeEventListener('xz:voice-mode', onVoiceMode);
      window.removeEventListener('xz:robot-action', onRobotAction);
      window.removeEventListener('xz:dignity', onDignity);
      window.removeEventListener('xz:ready', onReady);
    };
  }, [connectXiaozhi, kwsWakeupEnabled, loadDignityArtifacts, pauseAssistantListening, resumeAssistantAndStart, resumeAssistantListening, scheduleReconnect, speakViaTts, startListening, stopNormalRecording, stopTtsPlayback, stopWakeWordListening]);

  useEffect(() => {
    if (dignityMode) loadDignityArtifacts();
  }, [dignityMode, loadDignityArtifacts]);

  useEffect(() => {
    if (dignitySilenceTimerRef.current) {
      clearTimeout(dignitySilenceTimerRef.current);
      dignitySilenceTimerRef.current = null;
    }
    const canPrompt = activeApp === 'dignity'
      && dignityMode
      && dignityVoiceMode
      && !dignityPaused
      && connected
      && recording
      && aiState === 'idle'
      && !userSpeaking
      && !assistantHold
      && !inCall
      && !settingsOpen
      && !assistantToolsOpen
      && !dignityReadingKind;
    if (!canPrompt) return undefined;

    const promptIndex = Math.min(
      dignitySilencePromptCount,
      DIGNITY_SILENCE_DELAYS_MS.length - 1,
    );
    dignitySilenceTimerRef.current = setTimeout(() => {
      dignitySilenceTimerRef.current = null;
      void sendDignityAction('silence_prompt', {
        patient_id: DEVICE_ID,
        source: 'silence_timer',
        prompt_count: dignitySilencePromptCount,
      });
    }, DIGNITY_SILENCE_DELAYS_MS[promptIndex]);

    return () => {
      if (dignitySilenceTimerRef.current) {
        clearTimeout(dignitySilenceTimerRef.current);
        dignitySilenceTimerRef.current = null;
      }
    };
  }, [activeApp, aiState, assistantHold, assistantToolsOpen, connected, dignityMode, dignityPaused, dignityReadingKind, dignitySilencePromptCount, dignityVoiceMode, inCall, recording, sendDignityAction, settingsOpen, userSpeaking]);

  useEffect(() => {
    const nextSegments = segmentsFromTranscript(dignityStatus?.transcript);
    if (nextSegments.length) {
      setInterviewSegments(items => mergeInterviewSegments(items, nextSegments));
    }
  }, [dignityStatus?.transcript]);

  useEffect(() => {
    if (activeApp !== 'voice' && activeApp !== 'dignity') {
      stopNormalRecording();
      stopWakeWordListening();
      return;
    }
    if (!connected || !micOk || assistantHold || inCall) return;
    if (activeApp === 'dignity') {
      if (!dignityMode) return;
      if (dignityVoiceMode) startListening();
      return;
    }
    if (kwsWakeupEnabled && !ordinaryVoiceAwake) {
      stopNormalRecording();
      startWakeWordListening();
      return;
    }
    startListening();
  }, [activeApp, assistantHold, connected, dignityMode, dignityVoiceMode, inCall, kwsWakeupEnabled, micOk, ordinaryVoiceAwake, startListening, startWakeWordListening, stopNormalRecording, stopWakeWordListening]);

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
    if (settingsOpen || assistantToolsOpen) {
      pauseAssistantListening();
    } else if (activeApp === 'voice' || activeApp === 'dignity') {
      resumeAssistantListening();
    } else {
      pauseAssistantListening();
    }
  }, [activeApp, assistantToolsOpen, pauseAssistantListening, resumeAssistantListening, settingsOpen]);

  useEffect(() => () => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (callStateTimerRef.current) clearInterval(callStateTimerRef.current);
    if (speakingFallbackTimerRef.current) clearTimeout(speakingFallbackTimerRef.current);
    if (dignitySilenceTimerRef.current) clearTimeout(dignitySilenceTimerRef.current);
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
        const nextIncoming = {
          caller: { from: fromName || '家人', avatar: '家' },
          callType,
        };
        incomingRef.current = nextIncoming;
        setIncoming(nextIncoming);
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
          setOrdinaryMsg(detail.reply);
          await speakViaTts(detail.reply);
        }
      } else if (action === 'patient_voice_sleep') {
        if (!kwsWakeupEnabled) return;
        setOrdinaryVoiceAwake(false);
        ordinaryVoiceAwakeRef.current = false;
        setAiState('idle');
        setOrdinaryMsg(null);
        setOrdinaryLastHeard('');
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
        activeApp={activeApp}
        appTitle={APP_TITLES[activeApp] || ''}
        connected={connected}
        recording={recording}
        micOk={micOk}
        connectStatus={connectStatus}
        onHome={returnToHome}
      />
      <main className="patient-app-shell">
        {activeApp === 'home' && (
          <HomeScreen unread={unread} onOpenApp={openPatientApp} />
        )}

        {activeApp === 'voice' && (
          <section className="patient-app-page patient-app-page--voice">
          <ChatScreen
            aiState={aiState}
            msg={ordinaryMsg}
            lastHeard={ordinaryLastHeard}
            connected={connected}
            recording={recording}
            userSpeaking={userSpeaking}
            inputLevel={audioLevels.input}
            outputLevel={audioLevels.output}
            ordinaryVoiceAwake={ordinaryVoiceAwake || !kwsWakeupEnabled}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenAssistantTools={() => setAssistantToolsOpen(true)}
          />
          {robotDebugEnabled && <RobotActionDebugPanel actions={robotActionLog} />}
          </section>
        )}

        {activeApp === 'family' && (
          <section className="patient-app-page patient-app-page--family">
            <InboxScreen
              contacts={contacts}
              refreshContacts={loadContacts}
              eventTick={eventTick}
              maxUploadMb={maxUploadMb}
              onOpenContact={markThreadRead}
              onUnbindContact={unbindFamily}
            />
          </section>
        )}

        {activeApp === 'dignity' && (
          <section className="patient-app-page patient-app-page--dignity">
            {dignityDebugEnabled ? (
              <DignityDebugPanel
                turns={dignityTurns}
                status={dignityStatus}
                openingReply={dignityOpeningReply}
                busy={dignityDebugBusy}
                documentBusy={dignityDocumentBusy}
                documentConfirmBusy={dignityDocumentConfirmBusy}
                document={dignityDocument}
                documentUrl={dignityDocumentUrl}
                legacyCardBusy={legacyCardBusy}
                legacyCard={legacyCard}
                legacyCardImageUrl={legacyCardImageUrl}
                familyLetterBusy={familyLetterBusy}
                familyLetter={familyLetter}
                familyLetterImageUrl={familyLetterImageUrl}
                voiceMode={dignityVoiceMode}
                paused={dignityPaused}
                recording={recording}
                onRunTurn={runDignityDebugTurn}
                onReset={resetDignityDebug}
                onGenerateDocument={generateDignityDocument}
                onGenerateLegacyCard={generateLegacyCard}
                onGenerateFamilyLetter={generateFamilyLetter}
                onConfirmDocument={confirmDignityDocument}
                onDocumentChange={updateDignityDocument}
                onToggleVoiceMode={toggleDignityVoiceMode}
              />
            ) : (
              <DignityTherapyPanel
                status={dignityStatus}
                aiState={aiState}
                msg={dignityMsg}
                lastHeard={dignityLastHeard}
                connected={connected}
                userSpeaking={userSpeaking}
                inputLevel={audioLevels.input}
                outputLevel={audioLevels.output}
                openingReply={dignityOpeningReply}
                documentBusy={dignityDocumentBusy}
                documentConfirmBusy={dignityDocumentConfirmBusy}
                memoryBusy={dignityMemoryBusy}
                document={dignityDocument}
                documentUrl={dignityDocumentUrl}
                legacyCardBusy={legacyCardBusy}
                legacyCard={legacyCard}
                legacyCardImageUrl={legacyCardImageUrl}
                familyLetterBusy={familyLetterBusy}
                familyLetter={familyLetter}
                familyLetterImageUrl={familyLetterImageUrl}
                familyLetterTemplate={familyLetterTemplate}
                voiceMode={dignityVoiceMode}
                paused={dignityPaused}
                recording={recording}
                onReset={resetDignityDebug}
                onGenerateDocument={generateDignityDocument}
                onGenerateLegacyCard={generateLegacyCard}
                onLegacyCardChange={updateLegacyCard}
                onSaveLegacyCard={saveLegacyCard}
                onGenerateFamilyLetter={generateFamilyLetter}
                onFamilyLetterTemplateChange={setFamilyLetterTemplate}
                onFamilyLetterChange={updateFamilyLetter}
                onSaveFamilyLetter={saveFamilyLetter}
                onConfirmDocument={confirmDignityDocument}
                onDocumentChange={updateDignityDocument}
                onSaveMemory={saveDignityMemory}
                onToggleVoiceMode={toggleDignityVoiceMode}
                readingKind={dignityReadingKind}
                onReadDocument={() => readDignityContent('document', dignityDocument)}
                onReadLegacyCard={() => readDignityContent('card', legacyCard)}
                onReadFamilyLetter={() => readDignityContent('letter', familyLetter)}
                onStopReading={() => stopDignityReading()}
              />
            )}
          </section>
        )}

        {['digital', 'aroma', 'smartbed'].includes(activeApp) && (
          <ComingSoonScreen
            appId={activeApp}
            title={APP_TITLES[activeApp]}
            onHome={returnToHome}
          />
        )}
      </main>

      {(activeApp === 'voice' || activeApp === 'dignity') && (!connected || !micOk || connectStatus) && (
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
      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        voiceMode={voiceMode}
        onVoiceModeChange={handleVoiceModeChange}
      />
      <AssistantToolsModal
        open={assistantToolsOpen}
        active={assistantToolView}
        onChange={setAssistantToolView}
        onClose={() => setAssistantToolsOpen(false)}
        interviewSegments={interviewSegments}
        interviewAudioBusy={interviewAudioBusy}
        onToggleInterviewSegment={toggleInterviewSegmentDeleted}
        onSaveInterviewAudioSegments={saveInterviewAudioSegments}
      />
    </PaperBg>
  );
}

function AssistantToolsModal({
  open,
  active,
  onChange,
  onClose,
  interviewSegments,
  interviewAudioBusy,
  onToggleInterviewSegment,
  onSaveInterviewAudioSegments,
}) {
  if (!open) return null;
  return (
    <div style={assistantModalOverlayStyle}>
      <div style={assistantModalStyle}>
        <div style={assistantModalHeaderStyle}>
          <div>
            <div style={assistantModalTitleStyle}>助理功能</div>
            <div style={assistantModalSubStyle}>低频维护和审核工具</div>
          </div>
          <button type="button" onClick={onClose} style={assistantCloseButtonStyle}>关闭</button>
        </div>
        <div style={assistantModalTabsStyle}>
          <button type="button" onClick={() => onChange('audio')} style={assistantModalTabStyle(active === 'audio')}>
            访谈语音编辑
          </button>
          <button type="button" onClick={() => onChange('video')} style={assistantModalTabStyle(active === 'video')}>
            生命影像审核
          </button>
        </div>
        <div style={assistantModalBodyStyle}>
          {active === 'video' ? (
            <LegacyVideoScreen />
          ) : (
            <InterviewAudioEditor
              segments={interviewSegments}
              busy={interviewAudioBusy}
              onToggleSegment={onToggleInterviewSegment}
              onSave={onSaveInterviewAudioSegments}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function RobotActionDebugPanel({ actions }) {
  const latest = Array.isArray(actions) ? actions[0] : null;
  const items = Array.isArray(actions) ? actions : [];

  return (
    <div style={robotActionPanelStyle}>
      <div style={robotActionHeadStyle}>
        <div>
          <div style={robotActionTitleStyle}>硬件动作调试</div>
          <div style={robotActionSubStyle}>语音/访谈命中后的控制策略</div>
        </div>
        <div style={robotActionStatusStyle(latest?.status)}>
          {latest?.status || '等待'}
        </div>
      </div>
      {items.length ? (
        <div style={robotActionListStyle}>
          {items.map(item => (
            <div key={item.id} style={robotActionItemStyle}>
              <div style={robotActionMainStyle}>
                <span style={robotActionIdStyle}>{item.action_id || item.robot_action || 'unknown'}</span>
                <span style={robotActionMetaStyle}>{item.source || item.source_event || 'system'} · {item.time}</span>
              </div>
              <div style={robotActionReasonStyle}>
                {item.reason || item.strategy || item.eye_expression || '已收到动作事件'}
              </div>
              {item.params && Object.keys(item.params).length > 0 && (
                <pre style={robotActionParamsStyle}>{JSON.stringify(item.params)}</pre>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={robotActionEmptyStyle}>对机器人说“挥挥手”“过来一点”“停一下”后，这里会显示动作选择。</div>
      )}
    </div>
  );
}

const assistantModalOverlayStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 60,
  display: 'grid',
  placeItems: 'center',
  padding: 28,
  background: 'rgba(30,24,16,.28)',
  backdropFilter: 'blur(8px)',
};

const assistantModalStyle = {
  width: 'min(1040px, 94vw)',
  height: 'min(760px, 88vh)',
  display: 'grid',
  gridTemplateRows: 'auto auto minmax(0, 1fr)',
  borderRadius: 8,
  border: `1px solid ${C.mist}55`,
  background: 'rgba(255,250,242,.96)',
  boxShadow: '0 28px 60px rgba(31,23,14,.28)',
  overflow: 'hidden',
  color: C.ink,
  fontFamily: 'Noto Sans SC',
};

const assistantModalHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 16,
  padding: '20px 24px 14px',
  borderBottom: `1px solid ${C.mist}22`,
};

const assistantModalTitleStyle = {
  color: C.ink,
  fontSize: 24,
  lineHeight: 1.2,
  fontWeight: 700,
  fontFamily: 'Noto Serif SC, serif',
};

const assistantModalSubStyle = {
  color: C.inkFaint,
  fontSize: 14,
  lineHeight: 1.5,
  marginTop: 4,
};

const assistantCloseButtonStyle = {
  height: 38,
  padding: '0 16px',
  borderRadius: 8,
  border: `1px solid ${C.mist}66`,
  background: 'rgba(255,250,242,.8)',
  color: C.inkMid,
  fontSize: 15,
  fontWeight: 700,
  fontFamily: 'Noto Sans SC',
  cursor: 'pointer',
};

const assistantModalTabsStyle = {
  display: 'flex',
  gap: 10,
  padding: '12px 24px',
  borderBottom: `1px solid ${C.mist}22`,
  background: 'rgba(243,233,212,.45)',
};

const assistantModalTabStyle = (active) => ({
  height: 40,
  padding: '0 16px',
  borderRadius: 8,
  border: `1px solid ${active ? C.sage : C.mist}66`,
  background: active ? `${C.sage}22` : 'rgba(255,250,242,.72)',
  color: active ? C.ink : C.inkMid,
  fontSize: 15,
  fontWeight: active ? 700 : 500,
  fontFamily: 'Noto Sans SC',
  cursor: 'pointer',
});

const assistantModalBodyStyle = {
  minHeight: 0,
  overflow: 'auto',
  padding: 24,
};

const robotActionPanelStyle = {
  position: 'absolute',
  left: 20,
  right: 20,
  bottom: 18,
  zIndex: 16,
  display: 'grid',
  gap: 9,
  padding: '12px 14px',
  borderRadius: 8,
  border: `1px solid ${C.mist}55`,
  background: 'rgba(255,250,242,.88)',
  boxShadow: '0 16px 36px rgba(70, 55, 34, .16)',
  backdropFilter: 'blur(10px)',
  color: C.ink,
  fontFamily: 'Noto Sans SC',
  pointerEvents: 'none',
};

const robotActionHeadStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
};

const robotActionTitleStyle = {
  fontSize: 14,
  lineHeight: 1.2,
  fontWeight: 700,
  color: C.ink,
};

const robotActionSubStyle = {
  marginTop: 3,
  fontSize: 11,
  lineHeight: 1.3,
  color: C.inkFaint,
};

const robotActionStatusStyle = (status) => ({
  flex: '0 0 auto',
  minWidth: 58,
  height: 26,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '0 9px',
  borderRadius: 999,
  border: `1px solid ${status === 'rejected' ? '#C9877D' : C.sage}66`,
  background: status === 'rejected' ? 'rgba(201,135,125,.16)' : `${C.sage}20`,
  color: status === 'rejected' ? '#8E423B' : C.inkMid,
  fontSize: 12,
  fontWeight: 700,
});

const robotActionListStyle = {
  display: 'grid',
  gap: 7,
};

const robotActionItemStyle = {
  minWidth: 0,
  display: 'grid',
  gap: 4,
  paddingTop: 7,
  borderTop: `1px solid ${C.mist}22`,
};

const robotActionMainStyle = {
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: 10,
  minWidth: 0,
};

const robotActionIdStyle = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: 14,
  fontWeight: 800,
  color: C.ink,
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
};

const robotActionMetaStyle = {
  flex: '0 0 auto',
  fontSize: 11,
  color: C.inkFaint,
};

const robotActionReasonStyle = {
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: 12,
  lineHeight: 1.35,
  color: C.inkMid,
};

const robotActionParamsStyle = {
  margin: 0,
  maxHeight: 34,
  overflow: 'hidden',
  fontSize: 11,
  lineHeight: 1.35,
  color: C.inkFaint,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
};

const robotActionEmptyStyle = {
  paddingTop: 7,
  borderTop: `1px solid ${C.mist}22`,
  color: C.inkFaint,
  fontSize: 12,
  lineHeight: 1.45,
};
