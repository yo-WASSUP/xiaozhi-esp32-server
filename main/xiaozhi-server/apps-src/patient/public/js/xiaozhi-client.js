// 患者端 <-> xiaozhi-server 通信桥接层
// 复用 /test-assets/js 下的 WebSocket / 音频模块，
// 通过垫片（shim）隐藏掉它们对 test_page DOM 的依赖，
// 并以 window 事件的形式向 React 应用广播会话状态变化。

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
let clientId = localStorage.getItem('xz_tester_clientId');
if (!clientId) {
  clientId = (crypto && crypto.randomUUID) ? crypto.randomUUID()
    : 'c_' + Math.random().toString(36).slice(2) + Date.now().toString(36);
  localStorage.setItem('xz_tester_clientId', clientId);
}
ensureHiddenInput('deviceMac', deviceMac);
ensureHiddenInput('deviceName', 'patient-app');
ensureHiddenInput('clientId', clientId);

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
  import(`${TEST}/core/network/websocket.js?v=0127`),
  import(`${TEST}/core/audio/recorder.js?v=0127`),
  import(`${TEST}/core/audio/player.js?v=0127`),
  import(`${TEST}/core/audio/opus-codec.js?v=0127`),
]);

const wsHandler = wsMod.getWebSocketHandler();
const recorder = recMod.getAudioRecorder();
const player = playerMod.getAudioPlayer();

// ── 4. 桥接回调：把原模块的回调转成 window 事件 ──────────
let isConnected = false;
let isRemoteSpeaking = false;

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

wsHandler.onChatMessage = (text, isUser) => {
  if (isUser) {
    // 用户说话被识别出来：进入 thinking
    window.dispatchEvent(new CustomEvent('xz:stt', { detail: { text } }));
    window.dispatchEvent(new CustomEvent('xz:state', { detail: { state: 'thinking' } }));
  } else {
    // AI 回复文本（可能在 TTS 开始前后）
    window.dispatchEvent(new CustomEvent('xz:llm', { detail: { text } }));
  }
};

// ── 5. 暴露统一的客户端 API ──────────────────────────────
window.XiaozhiClient = {
  async init() {
    opusMod.checkOpusLoaded();
    opusMod.initOpusEncoder();
    await player.start();
    const ok = await recMod.checkMicrophoneAvailability();
    window.microphoneAvailable = ok;
    return ok;
  },

  async connect() {
    if (isConnected) return true;
    return await wsHandler.connect();
  },

  disconnect() {
    wsHandler.disconnect();
  },

  sendText(text) {
    return wsHandler.sendTextMessage(text);
  },

  async startRecording() {
    return await recorder.start();
  },

  stopRecording() {
    recorder.stop();
  },

  isConnected() { return isConnected; },
  isRemoteSpeaking() { return isRemoteSpeaking; },
};

// 让 React 侧知道桥已就绪
window.dispatchEvent(new Event('xz:ready'));
