// 患者端 <-> xiaozhi-server 通信桥接层
// 复用 /test-assets/js 下的 WebSocket / 音频模块，
// 通过垫片（shim）隐藏掉它们对 test_page DOM 的依赖，
// 并以 window 事件的形式向 React 应用广播会话状态变化。

let resolveXiaozhiBridge;
let rejectXiaozhiBridge;
const xiaozhiBridgeReady = new Promise((resolve, reject) => {
  resolveXiaozhiBridge = resolve;
  rejectXiaozhiBridge = reject;
});

window.XiaozhiClient = {
  ready: xiaozhiBridgeReady,
  async init() { return (await xiaozhiBridgeReady).init(); },
  async connect() { return (await xiaozhiBridgeReady).connect(); },
  disconnect() { return xiaozhiBridgeReady.then(c => c.disconnect()); },
  setVoiceMode(mode) { return xiaozhiBridgeReady.then(c => c.setVoiceMode(mode)); },
  sendClientState(payload) { return xiaozhiBridgeReady.then(c => c.sendClientState(payload)); },
  sendDignityAction(action, payload) { return xiaozhiBridgeReady.then(c => c.sendDignityAction(action, payload)); },
  sendText(text) { return xiaozhiBridgeReady.then(c => c.sendText(text)); },
  initWakeWord(config) { return xiaozhiBridgeReady.then(c => c.initWakeWord(config)); },
  startWakeWord() { return xiaozhiBridgeReady.then(c => c.startWakeWord()); },
  stopWakeWord() { return xiaozhiBridgeReady.then(c => c.stopWakeWord()); },
  releaseWakeWord() { return xiaozhiBridgeReady.then(c => c.releaseWakeWord()); },
  async startRecording(options) { return (await xiaozhiBridgeReady).startRecording(options); },
  stopRecording() { return xiaozhiBridgeReady.then(c => c.stopRecording()); },
  interrupt(reason) { return xiaozhiBridgeReady.then(c => c.interrupt(reason)); },
  listMicrophones() { return xiaozhiBridgeReady.then(c => c.listMicrophones()); },
  getMicrophoneDevice() { return xiaozhiBridgeReady.then(c => c.getMicrophoneDevice()); },
  setMicrophoneDevice(deviceId) { return xiaozhiBridgeReady.then(c => c.setMicrophoneDevice(deviceId)); },
  isConnected() { return false; },
  isRecording() { return false; },
  isRemoteSpeaking() { return false; },
};

(async function initXiaozhiBridge() {
if (document.readyState === 'loading') {
  await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, { once: true }));
}

const TEST = '/test-assets/js';

// ── 1. 垫片：补齐原模块期望的隐藏 DOM ────────────────────
function ensureHiddenInput(id, value = '') {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('input');
    el.id = id;
    el.type = 'hidden';
    document.body.appendChild(el);
  }
  el.value = value;
  return el;
}

const origin = window.location.origin;
ensureHiddenInput('serverUrl', '');
ensureHiddenInput('otaUrl', `${origin}/xiaozhi/ota/`);
ensureHiddenInput('scriptStatus', '');

// 设备信息：沿用 test_page 的 localStorage key，方便调试时和测试页共用
let deviceMac = localStorage.getItem('xz_tester_deviceMac');
if (!deviceMac) {
  const hex = '0123456789ABCDEF';
  deviceMac = Array.from({length:6}, () =>
    hex[Math.floor(Math.random()*16)] + hex[Math.floor(Math.random()*16)]
  ).join(':');
  localStorage.setItem('xz_tester_deviceMac', deviceMac);
}
localStorage.setItem('hospice_device_id', deviceMac);
let clientId = localStorage.getItem('xz_tester_clientId');
if (!clientId) {
  clientId = (crypto && crypto.randomUUID) ? crypto.randomUUID()
    : 'c_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
  localStorage.setItem('xz_tester_clientId', clientId);
}
ensureHiddenInput('deviceMac', deviceMac);
ensureHiddenInput('deviceName', 'patient-app');
ensureHiddenInput('clientId', clientId);
const savedVoiceMode = localStorage.getItem('anan_voice_mode') || 'doubao_s2s';
ensureHiddenInput('voiceMode', savedVoiceMode);

// ── 2. 垫片：stub uiController（原模块里硬引用） ────────
window.uiController = window.uiController || {
  init() {},
  startAIChatSession() {
    window.dispatchEvent(new CustomEvent('xz:session-start'));
  },
  addChatMessage(text, isUser) {
    window.dispatchEvent(new CustomEvent('xz:message', { detail: { text, isUser } }));
  },
  updateMicrophoneAvailability() {},
};

// ── 3. 动态加载原模块（ES module 形式） ──────────────────
const [
  wsMod,
  recMod,
  playerMod,
  opusMod,
] = await Promise.all([
  import(`${TEST}/core/network/websocket.js?v=0134`),
  import(`${TEST}/core/audio/recorder.js?v=0129`),
  import(`${TEST}/core/audio/player.js?v=0127`),
  import(`${TEST}/core/audio/opus-codec.js?v=0127`),
]);

const wsHandler = wsMod.getWebSocketHandler();
const recorder = recMod.getAudioRecorder();
const player = playerMod.getAudioPlayer();
let wakeWordMod = null;

// ── 4. 桥接回调：把原模块的回调转成 window 事件 ──────────
let isConnected = false;
let isRemoteSpeaking = false;
let audioLevelFrame = null;
let lastAudioLevelUpdate = 0;
let inputLevel = 0;
let outputLevel = 0;
let lastInterruptAt = 0;
const analyserBuffers = new WeakMap();
const MICROPHONE_STORAGE_KEY = 'anan_microphone_device_id';

function readAudioLevel(analyser) {
  if (!analyser) return 0;
  let data = analyserBuffers.get(analyser);
  if (!data || data.length !== analyser.fftSize) {
    data = new Uint8Array(analyser.fftSize);
    analyserBuffers.set(analyser, data);
  }
  analyser.getByteTimeDomainData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i += 1) {
    const sample = (data[i] - 128) / 128;
    sum += sample * sample;
  }
  const rms = Math.sqrt(sum / data.length);
  return Math.max(0, Math.min(1, (rms - 0.008) / 0.16));
}

function smoothLevel(previous, next) {
  const factor = next > previous ? 0.58 : 0.2;
  return previous + (next - previous) * factor;
}

function interruptRemoteSpeech(reason = 'user_speech', force = false) {
  const now = Date.now();
  player.clearAllAudio();
  if ((!isRemoteSpeaking && !force) || now - lastInterruptAt < 800) return false;
  const websocket = wsHandler.getWebSocket?.();
  if (!websocket || websocket.readyState !== WebSocket.OPEN) return false;

  lastInterruptAt = now;
  websocket.send(JSON.stringify({
    type: 'abort',
    session_id: wsHandler.currentSessionId || '',
    reason,
  }));
  isRemoteSpeaking = false;
  window.dispatchEvent(new CustomEvent('xz:barge-in', {
    detail: { reason }
  }));
  window.dispatchEvent(new CustomEvent('xz:state', {
    detail: { state: force ? 'idle' : 'listening' }
  }));
  return true;
}

function startAudioLevelMonitor() {
  if (audioLevelFrame) return;
  const update = (time) => {
    audioLevelFrame = requestAnimationFrame(update);
    if (time - lastAudioLevelUpdate < 66) return;
    lastAudioLevelUpdate = time;
    inputLevel = smoothLevel(inputLevel, readAudioLevel(recorder.getAnalyser?.()));
    outputLevel = smoothLevel(outputLevel, readAudioLevel(player.getAnalyser?.()));
    window.dispatchEvent(new CustomEvent('xz:audio-level', {
      detail: { input: inputLevel, output: outputLevel }
    }));
  };
  audioLevelFrame = requestAnimationFrame(update);
}

function displayText(text) {
  let value = text;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const parsed = JSON.parse(trimmed);
        value = parsed?.content || parsed?.text || value;
      } catch (_) {
        value = text;
      }
    }
  } else if (value && typeof value === 'object') {
    value = value.content || value.text || '';
  }
  return String(value || '')
    .replace(/<!--\s*emotion\s*:[\s\S]*?-->/gi, '')
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '')
    .trim();
}

wsHandler.onConnectionStateChange = (connected) => {
  isConnected = connected;
  window.dispatchEvent(new CustomEvent('xz:connection', { detail: { connected } }));
  if (!connected) {
    window.dispatchEvent(new CustomEvent('xz:state', { detail: { state: 'idle' } }));
  }
};

wsHandler.onSessionStateChange = (speaking) => {
  isRemoteSpeaking = speaking;
  window.dispatchEvent(new CustomEvent('xz:state', {
    detail: { state: speaking ? 'speaking' : 'idle' }
  }));
};

wsHandler.onAudioData = (detail = {}) => {
  window.dispatchEvent(new CustomEvent('xz:audio-playback-start', { detail }));
};

wsHandler.onChatMessage = (text, isUser, meta = {}) => {
  if (!isUser && typeof text === 'string' && text.includes('"type": "vad"')) {
    return;
  }
  const cleanText = displayText(text);
  if (!cleanText) return;
  if (isUser) {
    // 保持聆听画面，收到真实 TTS start 后再进入 speaking。
    window.dispatchEvent(new CustomEvent('xz:stt', { detail: { text: cleanText } }));
  } else {
    // AI 回复文本（可能在 TTS 开始前后）
    window.dispatchEvent(new CustomEvent('xz:llm', {
      detail: { text: cleanText, ...meta }
    }));
  }
};

wsHandler.onClientAction = (payload) => {
  window.dispatchEvent(new CustomEvent('xz:client-action', { detail: payload || {} }));
  if (payload?.action === 'robot_action') {
    window.dispatchEvent(new CustomEvent('xz:robot-action', { detail: payload || {} }));
    return;
  }
  window.dispatchEvent(new CustomEvent('xz:state', { detail: { state: 'idle' } }));
};

wsHandler.onDignityEvent = (payload) => {
  window.dispatchEvent(new CustomEvent('xz:dignity', { detail: payload || {} }));
};

wsHandler.onVoiceModeChange = (payload) => {
  window.dispatchEvent(new CustomEvent('xz:voice-mode', { detail: payload || {} }));
};

// ── 5. 暴露统一的客户端 API ──────────────────────────────
const realClient = {
  async init() {
    opusMod.checkOpusLoaded();
    opusMod.initOpusEncoder();
    await player.start();
    const savedDeviceId = localStorage.getItem(MICROPHONE_STORAGE_KEY) || '';
    recorder.setDeviceId(savedDeviceId);
    let ok = await recMod.checkMicrophoneAvailability(savedDeviceId);
    if (!ok && savedDeviceId) {
      localStorage.removeItem(MICROPHONE_STORAGE_KEY);
      recorder.setDeviceId(null);
      ok = await recMod.checkMicrophoneAvailability();
    }
    window.microphoneAvailable = ok;
    startAudioLevelMonitor();
    return ok;
  },

  async connect() {
    if (isConnected) return true;
    return await wsHandler.connect();
  },

  disconnect() {
    wsHandler.disconnect();
  },

  setVoiceMode(mode) {
    const nextMode = mode === 'cascade' ? 'cascade' : 'doubao_s2s';
    ensureHiddenInput('voiceMode', nextMode);
    localStorage.setItem('anan_voice_mode', nextMode);
    recorder.setAudioFormat(nextMode === 'doubao_s2s' ? 'pcm' : 'opus');
    return nextMode;
  },

  sendClientState(payload) {
    const ws = wsHandler.getWebSocket && wsHandler.getWebSocket();
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: 'hospice_client_state', ...(payload || {}) }));
    return true;
  },

  sendDignityAction(action, payload = {}) {
    const ws = wsHandler.getWebSocket && wsHandler.getWebSocket();
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: 'dignity', action, ...(payload || {}) }));
    return true;
  },

  sendText(text) {
    return wsHandler.sendTextMessage(text);
  },

  async initWakeWord(config) {
    wakeWordMod = wakeWordMod || await import('./patient-wakeword.js?v=1');
    return await wakeWordMod.initPatientWakeWord(config);
  },

  async startWakeWord() {
    if (!wakeWordMod) return false;
    return await wakeWordMod.startPatientWakeWord();
  },

  async stopWakeWord() {
    if (!wakeWordMod) return false;
    return await wakeWordMod.stopPatientWakeWord();
  },

  async releaseWakeWord() {
    if (!wakeWordMod) return false;
    await wakeWordMod.releasePatientWakeWord();
    return true;
  },

  async startRecording(options = {}) {
    if (options.callActive) {
      this.sendClientState({ call_active: true });
    }
    return await recorder.start();
  },

  stopRecording() {
    recorder.stop();
  },

  interrupt(reason = 'user_request') {
    return interruptRemoteSpeech(reason, true);
  },

  async listMicrophones() {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
      .filter(device => device.kind === 'audioinput')
      .map((device, index) => ({
        deviceId: device.deviceId,
        groupId: device.groupId,
        label: device.label || `麦克风 ${index + 1}`,
      }));
  },

  getMicrophoneDevice() {
    return localStorage.getItem(MICROPHONE_STORAGE_KEY) || '';
  },

  async setMicrophoneDevice(deviceId) {
    const nextDeviceId = String(deviceId || '');
    await recorder.switchDevice(nextDeviceId);
    if (nextDeviceId) {
      localStorage.setItem(MICROPHONE_STORAGE_KEY, nextDeviceId);
    } else {
      localStorage.removeItem(MICROPHONE_STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent('xz:microphone-change', {
      detail: { deviceId: nextDeviceId }
    }));
    return nextDeviceId;
  },

  isConnected() { return isConnected; },
  isRecording() { return !!recorder.isRecording; },
  isRemoteSpeaking() { return isRemoteSpeaking; },
};

// 让 React 侧知道桥已就绪
window.dispatchEvent(new Event('xz:ready'));
window.XiaozhiClient = Object.assign(window.XiaozhiClient, realClient);
resolveXiaozhiBridge(realClient);
window.dispatchEvent(new Event('xz:ready'));
})().catch((err) => {
  console.error('XiaozhiClient bootstrap failed', err);
  rejectXiaozhiBridge(err);
  window.dispatchEvent(new CustomEvent('xz:error', { detail: { error: err } }));
});
