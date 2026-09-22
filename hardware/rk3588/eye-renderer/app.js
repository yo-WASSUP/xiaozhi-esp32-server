const EXPRESSION_CONFIG = {
  attentive: {
    label: "attentive",
    gazeAmplitude: 10,
  },
  speak: {
    label: "speak",
    gazeAmplitude: 4,
  },
  gentle: {
    label: "gentle",
    gazeAmplitude: 3,
  },
  calm: {
    label: "calm",
    gazeAmplitude: 10,
  },
  concern: {
    label: "concern",
    gazeAmplitude: 2,
  },
  warm_smile: {
    label: "warm_smile",
    gazeAmplitude: 3,
  },
};

const ACTION_TO_EXPRESSION = {
  "eye.calm": "calm",
  "eye.warm_smile": "warm_smile",
  "eye.attentive": "attentive",
  "eye.speak": "speak",
  "eye.gentle": "gentle",
  "eye.concern": "concern",
};

const GAZE_TARGET_MIN_MS = 3000;
const GAZE_TARGET_MAX_MS = 5000;
const GAZE_TRANSITION_MIN_MS = 800;
const GAZE_TRANSITION_MAX_MS = 1200;

const statusElement = document.getElementById("status");
let reconnectTimer = null;
let gazeTimer = null;
let currentExpression = "";
let currentActionId = "eye.calm";

function setExpression(expression, connected = true, actionId = currentActionId) {
  const nextExpression = EXPRESSION_CONFIG[expression] ? expression : "calm";
  const expressionChanged = nextExpression !== currentExpression;
  currentExpression = nextExpression;
  currentActionId = actionId || currentActionId;
  document.body.dataset.expression = nextExpression;
  document.body.dataset.connected = String(connected);
  statusElement.textContent = connected
    ? `${currentActionId} / ${nextExpression}`
    : `${currentActionId} / ${nextExpression} / reconnecting`;

  if (expressionChanged) {
    centerGaze();
    scheduleNextGazeTarget(randomBetween(2200, 3000));
  } else if (!gazeTimer) {
    scheduleNextGazeTarget();
  }
}

function connect() {
  const socket = new WebSocket("ws://127.0.0.1:8765");

  socket.addEventListener("open", () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    setExpression(currentExpression, true, currentActionId);
  });

  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "eye.render") {
        const actionId = String(payload.action_id || "eye.calm");
        setExpression(ACTION_TO_EXPRESSION[actionId] || "calm", true, actionId);
      }
    } catch (error) {
      console.warn("invalid eye renderer message", error);
    }
  });

  socket.addEventListener("close", scheduleReconnect);
  socket.addEventListener("error", scheduleReconnect);
}

function scheduleReconnect() {
  setExpression(currentExpression, false, currentActionId);
  if (reconnectTimer) {
    return;
  }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 1000);
}

function scheduleNextGazeTarget(delayMs = randomBetween(GAZE_TARGET_MIN_MS, GAZE_TARGET_MAX_MS)) {
  if (gazeTimer) {
    clearTimeout(gazeTimer);
  }

  gazeTimer = setTimeout(() => {
    updateGazeTarget();
    scheduleNextGazeTarget();
  }, delayMs);
}

function centerGaze() {
  if (gazeTimer) {
    clearTimeout(gazeTimer);
    gazeTimer = null;
  }

  document.documentElement.style.setProperty("--gaze-duration", "720ms");
  document.documentElement.style.setProperty("--gaze-x", "0%");
  document.documentElement.style.setProperty("--gaze-y", "0%");
}

function updateGazeTarget() {
  const config = EXPRESSION_CONFIG[currentExpression] || EXPRESSION_CONFIG.calm;
  const amplitude = config.gazeAmplitude;
  const transitionMs = randomBetween(GAZE_TRANSITION_MIN_MS, GAZE_TRANSITION_MAX_MS);
  const x = randomBetween(-amplitude, amplitude);
  const y = randomBetween(-amplitude * 0.55, amplitude * 0.55);

  document.documentElement.style.setProperty("--gaze-duration", `${transitionMs}ms`);
  document.documentElement.style.setProperty("--gaze-x", `${x.toFixed(2)}%`);
  document.documentElement.style.setProperty("--gaze-y", `${y.toFixed(2)}%`);
}

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

const previewExpression = new URLSearchParams(window.location.search).get("expression");
const initialExpression = EXPRESSION_CONFIG[previewExpression] ? previewExpression : "calm";

setExpression(initialExpression, false, `eye.${initialExpression}`);
connect();
