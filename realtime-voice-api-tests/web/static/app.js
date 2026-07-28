const providerTabs = [...document.querySelectorAll(".provider-tab")];
const callButton = document.querySelector("#callButton");
const muteButton = document.querySelector("#muteButton");
const microphonePicker = document.querySelector("#microphonePicker");
const microphoneButton = document.querySelector("#microphoneButton");
const microphoneMenu = document.querySelector("#microphoneMenu");
const selectedMicrophone = document.querySelector("#selectedMicrophone");
const clearButton = document.querySelector("#clearButton");
const connectionState = document.querySelector("#connectionState");
const connectionLabel = document.querySelector("#connectionLabel");
const activeModel = document.querySelector("#activeModel");
const voiceState = document.querySelector("#voiceState");
const waveform = document.querySelector("#waveform");
const levelFill = document.querySelector("#levelFill");
const levelValue = document.querySelector("#levelValue");
const providerLatency = document.querySelector("#providerLatency");
const clientLatency = document.querySelector("#clientLatency");
const responseLatency = document.querySelector("#responseLatency");
const utteranceDuration = document.querySelector("#utteranceDuration");
const playbackBuffer = document.querySelector("#playbackBuffer");
const audioFormat = document.querySelector("#audioFormat");
const userLive = document.querySelector("#userLive");
const assistantLive = document.querySelector("#assistantLive");
const userHistory = document.querySelector("#userHistory");
const assistantHistory = document.querySelector("#assistantHistory");
const userTurnState = document.querySelector("#userTurnState");
const assistantTurnState = document.querySelector("#assistantTurnState");
const eventLog = document.querySelector("#eventLog");
const errorBanner = document.querySelector("#errorBanner");
const errorText = document.querySelector("#errorText");
const dismissError = document.querySelector("#dismissError");

const state = {
  selectedProvider: "openai",
  providers: new Map(),
  socket: null,
  ready: false,
  connecting: false,
  micEnabled: true,
  microphones: [],
  selectedMicrophoneId: localStorage.getItem("voice-lab-microphone") || "",
  stream: null,
  captureContext: null,
  outputContext: null,
  worklet: null,
  analyser: null,
  analyserData: null,
  animationFrame: null,
  silentGain: null,
  nextPlayAt: 0,
  audioSources: new Set(),
  turnStoppedAt: null,
  firstClientAudioSeen: false,
  currentText: { user: "", assistant: "" },
  histories: { user: [], assistant: [] },
};

const iconPaths = {
  mic: `
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
    <line x1="12" x2="12" y1="19" y2="22"/>
  `,
  "mic-off": `
    <line x1="2" x2="22" y1="2" y2="22"/>
    <path d="M18.89 18.89A7 7 0 0 1 5 12v-2"/>
    <path d="M15 9.34V5a3 3 0 0 0-5.68-1.33"/>
    <path d="M9 9v3a3 3 0 0 0 5.12 2.12"/>
    <line x1="12" x2="12" y1="19" y2="22"/>
  `,
  sliders: `
    <line x1="4" x2="4" y1="21" y2="14"/>
    <line x1="4" x2="4" y1="10" y2="3"/>
    <line x1="12" x2="12" y1="21" y2="12"/>
    <line x1="12" x2="12" y1="8" y2="3"/>
    <line x1="20" x2="20" y1="21" y2="16"/>
    <line x1="20" x2="20" y1="12" y2="3"/>
    <line x1="1" x2="7" y1="14" y2="14"/>
    <line x1="9" x2="15" y1="8" y2="8"/>
    <line x1="17" x2="23" y1="16" y2="16"/>
  `,
  "chevron-down": `<path d="m6 9 6 6 6-6"/>`,
  check: `<path d="m20 6-11 11-5-5"/>`,
  refresh: `
    <path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/>
    <path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>
  `,
  phone: `
    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.69 2.8a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.33 1.84.56 2.8.69A2 2 0 0 1 22 16.92Z"/>
  `,
  stop: `<rect width="14" height="14" x="5" y="5" rx="1"/>`,
  trash: `
    <path d="M3 6h18"/>
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
    <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    <line x1="10" x2="10" y1="11" y2="17"/>
    <line x1="14" x2="14" y1="11" y2="17"/>
  `,
  alert: `
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" x2="12" y1="8" y2="12"/>
    <line x1="12" x2="12.01" y1="16" y2="16"/>
  `,
  x: `
    <path d="M18 6 6 18"/>
    <path d="m6 6 12 12"/>
  `,
};

function iconSvg(name) {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
      viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      ${iconPaths[name] || ""}
    </svg>
  `;
}

function setIcon(slot, name) {
  if (!slot) {
    return;
  }
  slot.dataset.icon = name;
  slot.innerHTML = iconSvg(name);
}

function refreshIcons() {
  for (const slot of document.querySelectorAll(".icon-slot[data-icon]")) {
    setIcon(slot, slot.dataset.icon);
  }
}

function nowLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date());
}

function formatMs(value) {
  return Number.isFinite(value) ? `${Math.round(value)} ms` : "--";
}

function setConnection(status, label) {
  connectionState.dataset.state = status;
  connectionLabel.textContent = label;
}

function addEvent(kind, message, tone = "") {
  const row = document.createElement("div");
  row.className = "event-row";
  if (tone) {
    row.dataset.tone = tone;
  }
  const time = document.createElement("time");
  time.textContent = nowLabel();
  const eventKind = document.createElement("span");
  eventKind.className = "event-kind";
  eventKind.textContent = kind;
  const detail = document.createElement("p");
  detail.textContent = message;
  row.append(time, eventKind, detail);
  eventLog.prepend(row);
  while (eventLog.children.length > 40) {
    eventLog.lastElementChild.remove();
  }
}

function showError(message) {
  errorText.textContent = message;
  errorBanner.hidden = false;
  setConnection("error", "连接异常");
  addEvent("ERROR", message, "error");
}

function renderProviderState() {
  for (const tab of providerTabs) {
    const provider = state.providers.get(tab.dataset.provider);
    tab.classList.toggle("is-active", tab.dataset.provider === state.selectedProvider);
    tab.classList.toggle("is-configured", Boolean(provider?.configured));
    tab.classList.toggle("is-missing", provider ? !provider.configured : false);
    tab.disabled = state.connecting || state.ready;
    if (provider) {
      tab.title = provider.configured ? provider.model : "凭据未配置";
    }
  }
  const selected = state.providers.get(state.selectedProvider);
  activeModel.textContent = selected
    ? `${selected.name} · ${selected.model}`
    : "正在读取接口状态";
  callButton.disabled = state.connecting || Boolean(selected && !selected.configured);
  microphoneButton.disabled = state.connecting || state.ready;
}

function microphoneLabel(device, index) {
  return device.label || `麦克风 ${index + 1}`;
}

function selectedMicrophoneDevice() {
  return state.microphones.find(
    (device) => device.deviceId === state.selectedMicrophoneId,
  );
}

function updateMicrophoneButton() {
  const device = selectedMicrophoneDevice();
  selectedMicrophone.textContent = device
    ? microphoneLabel(device, state.microphones.indexOf(device))
    : "系统默认";
  microphoneButton.title = `选择麦克风：${selectedMicrophone.textContent}`;
}

function selectMicrophone(deviceId, label) {
  state.selectedMicrophoneId = deviceId;
  if (deviceId) {
    localStorage.setItem("voice-lab-microphone", deviceId);
  } else {
    localStorage.removeItem("voice-lab-microphone");
  }
  updateMicrophoneButton();
  closeMicrophoneMenu();
  addEvent("MIC", `输入设备：${label}`);
}

function buildMicrophoneOption(deviceId, label, selected) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "device-option";
  button.role = "menuitemradio";
  button.setAttribute("aria-checked", String(selected));

  const check = document.createElement("span");
  check.className = "device-option-check";
  check.innerHTML = selected ? iconSvg("check") : "";

  const text = document.createElement("span");
  text.textContent = label;
  button.append(check, text);
  button.addEventListener("click", () => selectMicrophone(deviceId, label));
  return button;
}

function renderMicrophoneMenu() {
  const options = [
    buildMicrophoneOption(
      "",
      "系统默认",
      !state.selectedMicrophoneId || !selectedMicrophoneDevice(),
    ),
  ];

  state.microphones.forEach((device, index) => {
    options.push(
      buildMicrophoneOption(
        device.deviceId,
        microphoneLabel(device, index),
        device.deviceId === state.selectedMicrophoneId,
      ),
    );
  });

  const separator = document.createElement("div");
  separator.className = "device-menu-separator";

  const refreshButton = document.createElement("button");
  refreshButton.type = "button";
  refreshButton.className = "device-option device-refresh";
  refreshButton.role = "menuitem";
  refreshButton.innerHTML = `${iconSvg("refresh")}<span>刷新设备</span>`;
  refreshButton.addEventListener("click", async () => {
    await refreshMicrophones(true);
    renderMicrophoneMenu();
  });

  microphoneMenu.replaceChildren(...options, separator, refreshButton);
}

async function refreshMicrophones(requestAccess = false) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    microphoneButton.disabled = true;
    selectedMicrophone.textContent = "浏览器不支持";
    return;
  }

  let devices = await navigator.mediaDevices.enumerateDevices();
  const hasLabels = devices.some(
    (device) => device.kind === "audioinput" && device.label,
  );
  if (requestAccess && !hasLabels) {
    const permissionStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
    });
    permissionStream.getTracks().forEach((track) => track.stop());
    devices = await navigator.mediaDevices.enumerateDevices();
  }

  state.microphones = devices.filter((device) => device.kind === "audioinput");
  if (
    state.selectedMicrophoneId &&
    !state.microphones.some(
      (device) => device.deviceId === state.selectedMicrophoneId,
    )
  ) {
    state.selectedMicrophoneId = "";
    localStorage.removeItem("voice-lab-microphone");
  }
  updateMicrophoneButton();
}

function closeMicrophoneMenu() {
  microphoneMenu.hidden = true;
  microphoneButton.setAttribute("aria-expanded", "false");
}

async function toggleMicrophoneMenu() {
  if (!microphoneMenu.hidden) {
    closeMicrophoneMenu();
    return;
  }
  try {
    await refreshMicrophones(true);
    renderMicrophoneMenu();
    microphoneMenu.hidden = false;
    microphoneButton.setAttribute("aria-expanded", "true");
  } catch (error) {
    showError(`无法读取麦克风设备：${error.message || String(error)}`);
  }
}

async function loadProviders() {
  const response = await fetch("/api/providers", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`接口状态读取失败: HTTP ${response.status}`);
  }
  const payload = await response.json();
  state.providers = new Map(payload.providers.map((item) => [item.id, item]));
  renderProviderState();
}

function renderLive(role) {
  const element = role === "user" ? userLive : assistantLive;
  const text = state.currentText[role];
  element.textContent = text || "--";
  element.classList.toggle("is-active", Boolean(text));
}

function commitTranscript(role, text) {
  const normalized = text.trim();
  if (!normalized) {
    return;
  }
  state.histories[role].unshift({ text: normalized, time: nowLabel() });
  state.histories[role] = state.histories[role].slice(0, 30);
  const container = role === "user" ? userHistory : assistantHistory;
  container.replaceChildren(
    ...state.histories[role].map((entry) => {
      const wrapper = document.createElement("article");
      wrapper.className = "transcript-entry";
      const paragraph = document.createElement("p");
      paragraph.textContent = entry.text;
      const time = document.createElement("time");
      time.textContent = entry.time;
      wrapper.append(paragraph, time);
      return wrapper;
    }),
  );
}

function handleTranscript(event) {
  const role = event.role;
  if (role !== "user" && role !== "assistant") {
    return;
  }
  if (event.delta) {
    state.currentText[role] += event.text;
  } else {
    state.currentText[role] = event.text;
  }
  renderLive(role);
  if (event.final) {
    commitTranscript(role, state.currentText[role]);
    state.currentText[role] = "";
    renderLive(role);
    if (role === "user") {
      userTurnState.textContent = "转写完成";
    } else {
      assistantTurnState.textContent = "回复完成";
    }
  }
}

function resetMetrics() {
  providerLatency.textContent = "--";
  clientLatency.textContent = "--";
  responseLatency.textContent = "--";
  utteranceDuration.textContent = "--";
  playbackBuffer.textContent = "0 ms";
}

function clearPlayback() {
  for (const source of state.audioSources) {
    try {
      source.stop();
    } catch {
      // Source may already have completed.
    }
  }
  state.audioSources.clear();
  state.nextPlayAt = state.outputContext?.currentTime || 0;
  playbackBuffer.textContent = "0 ms";
}

function playPcm(arrayBuffer, outputRate) {
  if (!state.outputContext || arrayBuffer.byteLength === 0) {
    return;
  }
  if (!state.firstClientAudioSeen && state.turnStoppedAt !== null) {
    clientLatency.textContent = formatMs(performance.now() - state.turnStoppedAt);
    state.firstClientAudioSeen = true;
  }

  const view = new DataView(arrayBuffer);
  const frameCount = Math.floor(arrayBuffer.byteLength / 2);
  const audioBuffer = state.outputContext.createBuffer(1, frameCount, outputRate);
  const channel = audioBuffer.getChannelData(0);
  for (let index = 0; index < frameCount; index += 1) {
    channel[index] = view.getInt16(index * 2, true) / 32768;
  }

  const source = state.outputContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(state.outputContext.destination);
  const startAt = Math.max(
    state.outputContext.currentTime + 0.012,
    state.nextPlayAt,
  );
  source.start(startAt);
  state.nextPlayAt = startAt + audioBuffer.duration;
  state.audioSources.add(source);
  source.onended = () => state.audioSources.delete(source);
}

function updatePlaybackMetric() {
  if (state.outputContext) {
    const queued = Math.max(
      0,
      (state.nextPlayAt - state.outputContext.currentTime) * 1000,
    );
    playbackBuffer.textContent = formatMs(queued);
  }
  window.setTimeout(updatePlaybackMetric, 200);
}

function handleServerEvent(event) {
  switch (event.type) {
    case "ready": {
      state.ready = true;
      state.connecting = false;
      setConnection("live", "通话中");
      callButton.classList.add("is-live");
      callButton.querySelector(".button-label").textContent = "结束通话";
      setIcon(callButton.querySelector(".icon-slot"), "stop");
      muteButton.disabled = false;
      activeModel.textContent = `${event.model} · ${event.input_rate / 1000}k → ${event.output_rate / 1000}k`;
      audioFormat.textContent = `PCM16 · IN ${event.input_rate / 1000} kHz · OUT ${event.output_rate / 1000} kHz`;
      addEvent("READY", `${event.provider} / ${event.model}`, "success");
      renderProviderState();
      refreshIcons();
      break;
    }
    case "status":
      if (event.state === "connecting") {
        setConnection("connecting", "连接接口");
      }
      break;
    case "speech_started":
      clearPlayback();
      voiceState.textContent = "正在说话";
      userTurnState.textContent = "识别中";
      assistantTurnState.textContent = "已打断";
      state.currentText.user = "";
      renderLive("user");
      addEvent("VAD", "检测到用户语音");
      break;
    case "speech_stopped":
      voiceState.textContent = "处理中";
      userTurnState.textContent = "话轮结束";
      utteranceDuration.textContent = formatMs(event.utterance_ms);
      state.turnStoppedAt = performance.now();
      state.firstClientAudioSeen = false;
      addEvent("TURN", `用户话轮 ${formatMs(event.utterance_ms)}`);
      break;
    case "transcript":
      handleTranscript(event);
      break;
    case "response_started":
      assistantTurnState.textContent = "生成中";
      state.currentText.assistant = "";
      renderLive("assistant");
      break;
    case "latency":
      providerLatency.textContent = formatMs(event.first_audio_ms);
      addEvent("LATENCY", `模型首包 ${formatMs(event.first_audio_ms)}`);
      break;
    case "response_done":
      responseLatency.textContent = formatMs(event.response_ms);
      assistantTurnState.textContent =
        event.status === "completed" ? "回复完成" : event.status;
      voiceState.textContent = "正在聆听";
      addEvent(
        "RESPONSE",
        `${event.status} / ${formatMs(event.response_ms)}`,
        "success",
      );
      break;
    case "error":
      showError(event.message || "接口返回未知错误");
      stopSession(false);
      break;
    default:
      break;
  }
}

async function initializeAudio(inputRate) {
  const audioConstraints = {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  if (state.selectedMicrophoneId) {
    audioConstraints.deviceId = { exact: state.selectedMicrophoneId };
  }
  state.stream = await navigator.mediaDevices.getUserMedia({
    audio: audioConstraints,
  });
  const activeTrack = state.stream.getAudioTracks()[0];
  if (activeTrack?.label) {
    selectedMicrophone.textContent = activeTrack.label;
    addEvent("MIC", `正在使用：${activeTrack.label}`, "success");
  }
  state.captureContext = new AudioContext({ latencyHint: "interactive" });
  state.outputContext = new AudioContext({ latencyHint: "interactive" });
  await Promise.all([
    state.captureContext.resume(),
    state.outputContext.resume(),
    state.captureContext.audioWorklet.addModule("/static/pcm-worklet.js"),
  ]);

  const source = state.captureContext.createMediaStreamSource(state.stream);
  state.analyser = state.captureContext.createAnalyser();
  state.analyser.fftSize = 512;
  state.analyser.smoothingTimeConstant = 0.72;
  state.analyserData = new Uint8Array(state.analyser.fftSize);
  state.worklet = new AudioWorkletNode(state.captureContext, "pcm-capture", {
    processorOptions: { targetRate: inputRate },
  });
  state.silentGain = state.captureContext.createGain();
  state.silentGain.gain.value = 0;
  source.connect(state.analyser);
  source.connect(state.worklet);
  state.worklet.connect(state.silentGain);
  state.silentGain.connect(state.captureContext.destination);
  state.worklet.port.onmessage = (message) => {
    if (
      state.ready &&
      state.micEnabled &&
      state.socket?.readyState === WebSocket.OPEN
    ) {
      state.socket.send(message.data);
    }
  };
  drawWaveform();
}

function drawWaveform() {
  const context = waveform.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, waveform.clientWidth);
  const height = Math.max(1, waveform.clientHeight);
  if (waveform.width !== Math.floor(width * ratio)) {
    waveform.width = Math.floor(width * ratio);
    waveform.height = Math.floor(height * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#37c494";
  context.lineWidth = 2;
  context.beginPath();

  let level = 0;
  if (state.analyser && state.analyserData) {
    state.analyser.getByteTimeDomainData(state.analyserData);
    for (let index = 0; index < state.analyserData.length; index += 1) {
      const normalized = (state.analyserData[index] - 128) / 128;
      level += normalized * normalized;
      const x = (index / (state.analyserData.length - 1)) * width;
      const y = height / 2 + normalized * height * 0.4;
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    }
    level = Math.min(1, Math.sqrt(level / state.analyserData.length) * 4.5);
  } else {
    context.moveTo(0, height / 2);
    context.lineTo(width, height / 2);
  }
  context.stroke();
  const percent = Math.round(level * 100);
  levelFill.style.width = `${percent}%`;
  levelValue.textContent = `${percent}%`;
  state.animationFrame = requestAnimationFrame(drawWaveform);
}

async function startSession() {
  const provider = state.providers.get(state.selectedProvider);
  if (!provider?.configured) {
    showError(`${provider?.name || "当前接口"}的凭据未配置`);
    return;
  }

  errorBanner.hidden = true;
  resetMetrics();
  state.connecting = true;
  state.micEnabled = true;
  setConnection("connecting", "请求麦克风");
  callButton.disabled = true;
  renderProviderState();

  try {
    await initializeAudio(provider.input_rate);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    state.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    state.socket.binaryType = "arraybuffer";
    state.socket.onopen = () => {
      setConnection("connecting", "连接接口");
      state.socket.send(
        JSON.stringify({
          type: "start",
          provider: state.selectedProvider,
        }),
      );
    };
    state.socket.onmessage = (message) => {
      if (typeof message.data === "string") {
        handleServerEvent(JSON.parse(message.data));
      } else {
        playPcm(message.data, provider.output_rate);
      }
    };
    state.socket.onerror = () => {
      showError("本地 WebSocket 连接失败");
    };
    state.socket.onclose = () => {
      if (state.ready || state.connecting) {
        stopSession(false);
      }
    };
  } catch (error) {
    showError(error.message || String(error));
    await stopSession(false);
  }
}

async function stopSession(notifyServer = true) {
  const socket = state.socket;
  state.socket = null;
  state.ready = false;
  state.connecting = false;
  if (notifyServer && socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop" }));
  }
  socket?.close();
  clearPlayback();
  if (state.animationFrame) {
    cancelAnimationFrame(state.animationFrame);
    state.animationFrame = null;
  }
  state.worklet?.disconnect();
  state.silentGain?.disconnect();
  state.stream?.getTracks().forEach((track) => track.stop());
  await Promise.allSettled([
    state.captureContext?.close(),
    state.outputContext?.close(),
  ]);
  state.stream = null;
  state.captureContext = null;
  state.outputContext = null;
  state.worklet = null;
  state.analyser = null;
  state.analyserData = null;
  state.audioSources.clear();
  state.nextPlayAt = 0;
  muteButton.disabled = true;
  muteButton.classList.remove("is-muted");
  callButton.classList.remove("is-live");
  callButton.querySelector(".button-label").textContent = "开始通话";
  setIcon(callButton.querySelector(".icon-slot"), "phone");
  voiceState.textContent = "静音";
  setConnection("idle", "未连接");
  userTurnState.textContent = "等待输入";
  assistantTurnState.textContent = "等待响应";
  renderProviderState();
  refreshIcons();
}

function toggleMute() {
  state.micEnabled = !state.micEnabled;
  muteButton.classList.toggle("is-muted", !state.micEnabled);
  muteButton.title = state.micEnabled ? "关闭麦克风" : "打开麦克风";
  setIcon(
    muteButton.querySelector(".icon-slot"),
    state.micEnabled ? "mic" : "mic-off",
  );
  voiceState.textContent = state.micEnabled ? "正在聆听" : "麦克风关闭";
  addEvent("MIC", state.micEnabled ? "麦克风已开启" : "麦克风已关闭");
  refreshIcons();
}

providerTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    if (state.ready || state.connecting) {
      return;
    }
    state.selectedProvider = tab.dataset.provider;
    renderProviderState();
  });
});

callButton.addEventListener("click", () => {
  if (state.ready || state.connecting) {
    stopSession();
  } else {
    startSession();
  }
});

muteButton.addEventListener("click", toggleMute);
microphoneButton.addEventListener("click", toggleMicrophoneMenu);
clearButton.addEventListener("click", () => {
  state.currentText = { user: "", assistant: "" };
  state.histories = { user: [], assistant: [] };
  userHistory.replaceChildren();
  assistantHistory.replaceChildren();
  renderLive("user");
  renderLive("assistant");
  addEvent("SYSTEM", "对话记录已清空");
});
dismissError.addEventListener("click", () => {
  errorBanner.hidden = true;
});
document.addEventListener("click", (event) => {
  if (!microphonePicker.contains(event.target)) {
    closeMicrophoneMenu();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeMicrophoneMenu();
  }
});
if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener("devicechange", () => {
    refreshMicrophones().catch(() => {});
  });
}
window.addEventListener("beforeunload", () => {
  state.socket?.close();
  state.stream?.getTracks().forEach((track) => track.stop());
});

refreshIcons();
updatePlaybackMetric();
refreshMicrophones().catch(() => {
  selectedMicrophone.textContent = "读取失败";
});
loadProviders().catch((error) => showError(error.message || String(error)));
