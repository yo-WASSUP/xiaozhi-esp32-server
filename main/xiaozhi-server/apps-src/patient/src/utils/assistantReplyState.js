export function mergeAssistantDisplayText(current, incoming) {
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

export function createAssistantReplyState(overrides = {}) {
  return {
    sentenceId: '',
    spokenText: '',
    pendingFinalText: '',
    displayText: '',
    ttsActive: false,
    final: false,
    ...overrides,
  };
}

export function reduceAssistantReply(currentState, event = {}) {
  let state = createAssistantReplyState(currentState);
  const sentenceId = String(event.sentenceId || '');
  if (event.type === 'tts-stopped') {
    if (sentenceId && state.sentenceId && sentenceId !== state.sentenceId) {
      return state;
    }
    if (state.pendingFinalText) {
      return {
        ...state,
        displayText: state.pendingFinalText,
        pendingFinalText: '',
        ttsActive: false,
        final: true,
      };
    }
    return { ...state, ttsActive: false };
  }

  if (sentenceId && state.sentenceId && sentenceId !== state.sentenceId) {
    state = createAssistantReplyState({ sentenceId });
  } else if (sentenceId && !state.sentenceId) {
    state = { ...state, sentenceId };
  }

  if (event.type === 'tts-started') {
    return { ...state, ttsActive: true };
  }

  if (event.type !== 'assistant-text') return state;

  const text = String(event.text || '').trim();
  if (!text) return state;

  if (event.source === 'tts') {
    const spokenText = mergeAssistantDisplayText(state.spokenText, text);
    const pendingFinalText = state.pendingFinalText
      || (state.final ? state.displayText : '');
    return {
      ...state,
      spokenText,
      pendingFinalText,
      displayText: spokenText,
      ttsActive: true,
      final: false,
    };
  }

  if (event.final) {
    if (state.ttsActive) {
      return { ...state, pendingFinalText: text, final: false };
    }
    return {
      ...state,
      pendingFinalText: '',
      displayText: text,
      final: true,
    };
  }

  if (state.final) return state;
  return {
    ...state,
    displayText: mergeAssistantDisplayText(state.displayText, text),
  };
}
