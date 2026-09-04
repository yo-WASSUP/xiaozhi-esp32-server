import assert from 'node:assert/strict';
import test from 'node:test';

import { createVideoHandoff } from './videoHandoff.js';


test('keeps the current video visible until the requested video has a first frame', async () => {
  const commits = [];
  let releaseFirstFrame;
  const handoff = createVideoHandoff('idle', (next, previous) => {
    commits.push({ next, previous });
  });

  const pending = handoff.request('listening', () => new Promise(resolve => {
    releaseFirstFrame = resolve;
  }));

  assert.equal(handoff.activeState, 'idle');
  assert.deepEqual(commits, []);

  releaseFirstFrame();
  await pending;

  assert.equal(handoff.activeState, 'listening');
  assert.deepEqual(commits, [{ next: 'listening', previous: 'idle' }]);
});

test('ignores an older handoff when a newer state is requested', async () => {
  const releases = {};
  const commits = [];
  const handoff = createVideoHandoff('idle', (next, previous) => {
    commits.push({ next, previous });
  });
  const prepare = state => new Promise(resolve => {
    releases[state] = resolve;
  });

  const listening = handoff.request('listening', prepare);
  const speaking = handoff.request('speaking', prepare);

  releases.speaking();
  await speaking;
  releases.listening();
  await listening;

  assert.equal(handoff.activeState, 'speaking');
  assert.deepEqual(commits, [{ next: 'speaking', previous: 'idle' }]);
});

test('cancels a pending handoff when the owner is disposed', async () => {
  let releaseFirstFrame;
  const commits = [];
  const handoff = createVideoHandoff('idle', (next, previous) => {
    commits.push({ next, previous });
  });

  const pending = handoff.request('listening', () => new Promise(resolve => {
    releaseFirstFrame = resolve;
  }));
  handoff.cancel();
  releaseFirstFrame();
  await pending;

  assert.equal(handoff.activeState, 'idle');
  assert.deepEqual(commits, []);
});

test('returning to the active state cancels a pending different state', async () => {
  let releaseFirstFrame;
  const commits = [];
  const handoff = createVideoHandoff('idle', (next, previous) => {
    commits.push({ next, previous });
  });

  const listening = handoff.request('listening', () => new Promise(resolve => {
    releaseFirstFrame = resolve;
  }));
  await handoff.request('idle', () => Promise.resolve());
  releaseFirstFrame();
  await listening;

  assert.equal(handoff.activeState, 'idle');
  assert.deepEqual(commits, []);
});
