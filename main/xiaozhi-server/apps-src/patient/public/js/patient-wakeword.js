// Patient-side wake word bridge.
// Audio stays out of the normal ASR path while waiting for wakeup. It is sent
// only to the hospice KWS websocket backed by sherpa-onnx.

let activeConfig = null;
let ws = null;
let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let listening = false;
let ready = false;
let lifecycleQueue = Promise.resolve();

function dispatch(type, detail = {}) {
  window.dispatchEvent(new CustomEvent(type, { detail }));
}

function normalizeConfig(config = {}) {
  const sherpaConfig = config.sherpa_onnx || config.sherpaOnnx || {};
  return {
    deviceId: config.device_id || '',
    enabled: config.enabled !== false,
    mode: String(config.mode || 'sherpa_onnx_kws').toLowerCase(),
    threshold: Number(config.threshold || 0.50),
    endpoint: sherpaConfig.endpoint || sherpaConfig.ws_endpoint || '/api/hospice/wakeword/ws',
    sampleRate: Number(sherpaConfig.sample_rate || sherpaConfig.sampleRate || 16000),
  };
}

function wsUrl(path) {
  if (/^wss?:\/\//.test(path)) return path;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${path.startsWith('/') ? path : `/${path}`}`;
}

function floatToInt16(samples) {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] || 0));
    out[i] = s < 0 ? s * 32768 : s * 32767;
  }
  return out;
}

function closeSocket() {
  if (!ws) return;
  try { ws.close(); } catch (_) { }
  ws = null;
}

function connectWakeWordSocket(sampleRate) {
  closeSocket();
  ready = false;
  dispatch('xz:wakeword-state', { state: 'loading', mode: 'sherpa_onnx_kws' });

  return new Promise((resolve, reject) => {
    const endpoint = new URL(wsUrl(activeConfig.endpoint));
    endpoint.searchParams.set('role', 'patient');
    endpoint.searchParams.set('device_id', activeConfig.deviceId);
    const socket = new WebSocket(endpoint.href);
    ws = socket;
    socket.binaryType = 'arraybuffer';

    const timer = window.setTimeout(() => {
      reject(new Error('KWS websocket connection timed out'));
      try { socket.close(); } catch (_) { }
    }, 8000);

    socket.onopen = () => {
      socket.send(JSON.stringify({ type: 'start', sample_rate: sampleRate, threshold: activeConfig.threshold }));
    };

    socket.onmessage = (event) => {
      let payload = null;
      try { payload = JSON.parse(event.data); } catch (_) { return; }

      if (payload.type === 'ready' || payload.type === 'started') {
        ready = true;
        window.clearTimeout(timer);
        dispatch('xz:wakeword-state', { state: listening ? 'listening' : 'ready', mode: 'sherpa_onnx_kws' });
        resolve(true);
        return;
      }

      if (payload.type === 'wake') {
        dispatch('xz:wakeword-detected', {
          label: payload.keyword || 'wakeword',
          result: payload,
        });
        return;
      }

      if (payload.type === 'error') {
        dispatch('xz:wakeword-state', {
          state: 'error',
          mode: 'sherpa_onnx_kws',
          message: payload.message || 'KWS error',
        });
      }
    };

    socket.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error('KWS websocket error'));
    };

    socket.onclose = () => {
      if (ws === socket) {
        ws = null;
        ready = false;
      }
      if (listening) {
        dispatch('xz:wakeword-state', { state: 'stopped', mode: 'sherpa_onnx_kws' });
      }
    };
  });
}

function createProcessor(context) {
  const processor = context.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (event) => {
    if (!listening || !ready || !ws || ws.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);
    const pcm16 = floatToInt16(input);
    ws.send(pcm16.buffer);
  };
  return processor;
}

export async function initPatientWakeWord(config) {
  activeConfig = normalizeConfig(config);
  if (!activeConfig.enabled || activeConfig.mode !== 'sherpa_onnx_kws') {
    dispatch('xz:wakeword-state', { state: 'disabled', mode: activeConfig.mode });
    return false;
  }
  dispatch('xz:wakeword-state', { state: 'ready', mode: 'sherpa_onnx_kws' });
  return true;
}

function runLifecycle(task) {
  const operation = lifecycleQueue.then(task, task);
  lifecycleQueue = operation.catch(() => {});
  return operation;
}

async function stopPatientWakeWordNow() {
  if (!listening && !ws && !mediaStream && !audioContext) return false;
  listening = false;
  try { sourceNode?.disconnect(); } catch (_) { }
  try { processorNode?.disconnect(); } catch (_) { }
  try { await audioContext?.close?.(); } catch (_) { }
  mediaStream?.getTracks?.().forEach(track => track.stop());
  sourceNode = null;
  processorNode = null;
  mediaStream = null;
  audioContext = null;
  closeSocket();
  dispatch('xz:wakeword-state', { state: 'ready', mode: 'sherpa_onnx_kws' });
  return true;
}

async function startPatientWakeWordNow() {
  if (!activeConfig) return false;
  if (listening) return true;

  const requestedSampleRate = activeConfig.sampleRate || 16000;
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: requestedSampleRate });
    if (audioContext.state === 'suspended') await audioContext.resume();

    const microphoneDeviceId = localStorage.getItem('anan_microphone_device_id') || '';
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        ...(microphoneDeviceId ? { deviceId: { exact: microphoneDeviceId } } : {}),
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });

    sourceNode = audioContext.createMediaStreamSource(mediaStream);
    processorNode = createProcessor(audioContext);
    sourceNode.connect(processorNode);
    processorNode.connect(audioContext.destination);

    listening = true;
    await connectWakeWordSocket(audioContext.sampleRate || requestedSampleRate);
  } catch (error) {
    await stopPatientWakeWordNow();
    throw error;
  }
  dispatch('xz:wakeword-state', { state: 'listening', mode: 'sherpa_onnx_kws' });
  return true;
}

export function startPatientWakeWord() {
  return runLifecycle(startPatientWakeWordNow);
}

export function stopPatientWakeWord() {
  return runLifecycle(stopPatientWakeWordNow);
}

export async function releasePatientWakeWord() {
  await stopPatientWakeWord();
  ready = false;
}

export function getPatientWakeWordState() {
  return {
    ready,
    listening,
    mode: activeConfig?.mode || 'sherpa_onnx_kws',
  };
}
