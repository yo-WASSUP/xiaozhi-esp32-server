import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createAssistantReplyState,
  reduceAssistantReply,
} from './assistantReplyState.js';


test('final LLM text waits while the current TTS sentence is playing', () => {
  let state = createAssistantReplyState();
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'tts',
    sentenceId: 'weather-turn',
    text: '我帮您看看成都的天气哈。',
  });
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'llm',
    final: true,
    sentenceId: 'weather-turn',
    text: '今天成都多云，32度，有点热。',
  });

  assert.equal(state.displayText, '我帮您看看成都的天气哈。');
  assert.equal(state.pendingFinalText, '今天成都多云，32度，有点热。');
  assert.equal(state.final, false);
});

test('cached final text becomes visible after TTS playback stops', () => {
  let state = createAssistantReplyState();
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'tts',
    sentenceId: 'weather-turn',
    text: '我帮您看看成都的天气哈。',
  });
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'llm',
    final: true,
    sentenceId: 'weather-turn',
    text: '今天成都多云，32度，有点热。',
  });
  state = reduceAssistantReply(state, { type: 'tts-stopped' });

  assert.equal(state.displayText, '今天成都多云，32度，有点热。');
  assert.equal(state.pendingFinalText, '');
  assert.equal(state.ttsActive, false);
  assert.equal(state.final, true);
});

test('TTS start protects the display before the first sentence arrives', () => {
  let state = createAssistantReplyState();
  state = reduceAssistantReply(state, {
    type: 'tts-started',
    sentenceId: 'weather-turn',
  });
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'llm',
    final: true,
    sentenceId: 'weather-turn',
    text: '今天成都多云，32度。',
  });

  assert.equal(state.displayText, '');
  assert.equal(state.pendingFinalText, '今天成都多云，32度。');
  assert.equal(state.ttsActive, true);
});

test('final text remains canonical when TTS starts after the LLM completes', () => {
  let state = createAssistantReplyState();
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'llm',
    final: true,
    sentenceId: 'short-turn',
    text: '成都今天多云。',
  });
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'tts',
    sentenceId: 'short-turn',
    text: '成都今天多云。',
  });

  assert.equal(state.displayText, '成都今天多云。');
  assert.equal(state.pendingFinalText, '成都今天多云。');
  assert.equal(state.final, false);

  state = reduceAssistantReply(state, { type: 'tts-stopped' });
  assert.equal(state.displayText, '成都今天多云。');
  assert.equal(state.final, true);
});

test('a new sentence id cannot inherit cached text from the previous turn', () => {
  let state = createAssistantReplyState({
    sentenceId: 'old-turn',
    spokenText: '旧回复',
    pendingFinalText: '旧的完整回复',
    displayText: '旧回复',
    ttsActive: true,
  });
  state = reduceAssistantReply(state, {
    type: 'assistant-text',
    source: 'tts',
    sentenceId: 'new-turn',
    text: '新的回复',
  });

  assert.equal(state.sentenceId, 'new-turn');
  assert.equal(state.displayText, '新的回复');
  assert.equal(state.pendingFinalText, '');
});

test('a stale TTS stop cannot finalize the active turn', () => {
  const state = createAssistantReplyState({
    sentenceId: 'new-turn',
    spokenText: '正在播报新回复',
    pendingFinalText: '新的完整回复',
    displayText: '正在播报新回复',
    ttsActive: true,
  });

  const next = reduceAssistantReply(state, {
    type: 'tts-stopped',
    sentenceId: 'old-turn',
  });

  assert.equal(next.displayText, '正在播报新回复');
  assert.equal(next.pendingFinalText, '新的完整回复');
  assert.equal(next.ttsActive, true);
  assert.equal(next.final, false);
});
