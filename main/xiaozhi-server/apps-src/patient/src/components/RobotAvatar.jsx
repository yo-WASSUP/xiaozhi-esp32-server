import { useEffect, useRef, useState } from 'react';
import RobotAvatarSprite from './RobotAvatarSprite';
import RobotAvatarVideo from './RobotAvatarVideo';

const FALLBACK_MODE = 'sprite';
const PLAYBACK_END_LEVEL = 0.001;
const PLAYBACK_RELEASE_MS = 600;
let cachedMode = null;
let modeRequest = null;

function normalizeMode(value) {
  return String(value || '').toLowerCase() === 'video' ? 'video' : FALLBACK_MODE;
}

function loadAvatarMode() {
  if (cachedMode) return Promise.resolve(cachedMode);
  if (!modeRequest) {
    modeRequest = fetch('/api/hospice/config')
      .then(response => {
        if (!response.ok) throw new Error(`avatar config request failed: ${response.status}`);
        return response.json();
      })
      .then(config => {
        cachedMode = normalizeMode(config?.robot_avatar_mode);
        return cachedMode;
      })
      .catch(() => {
        cachedMode = FALLBACK_MODE;
        return cachedMode;
      });
  }
  return modeRequest;
}

export default function RobotAvatar({ state = 'idle', outputLevel = 0, ...props }) {
  const [mode, setMode] = useState(cachedMode || FALLBACK_MODE);
  const [audioPlaybackActive, setAudioPlaybackActive] = useState(false);
  const stateRef = useRef(state);
  const playbackReleaseTimerRef = useRef(null);

  useEffect(() => {
    let active = true;
    loadAvatarMode().then(nextMode => {
      if (active) setMode(nextMode);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => { stateRef.current = state; }, [state]);

  useEffect(() => {
    const onAudioPlaybackStart = () => {
      if (stateRef.current !== 'speaking') return;
      if (playbackReleaseTimerRef.current) {
        clearTimeout(playbackReleaseTimerRef.current);
        playbackReleaseTimerRef.current = null;
      }
      setAudioPlaybackActive(true);
    };
    window.addEventListener('xz:audio-playback-start', onAudioPlaybackStart);
    return () => window.removeEventListener('xz:audio-playback-start', onAudioPlaybackStart);
  }, []);

  useEffect(() => {
    const clearReleaseTimer = () => {
      if (!playbackReleaseTimerRef.current) return;
      clearTimeout(playbackReleaseTimerRef.current);
      playbackReleaseTimerRef.current = null;
    };
    const level = Math.max(0, Number(outputLevel) || 0);

    if (state === 'speaking') {
      clearReleaseTimer();
      if (level > PLAYBACK_END_LEVEL) setAudioPlaybackActive(true);
      return;
    }
    if (state !== 'idle') {
      clearReleaseTimer();
      setAudioPlaybackActive(false);
      return;
    }
    if (!audioPlaybackActive) return;
    if (level > PLAYBACK_END_LEVEL) {
      clearReleaseTimer();
      return;
    }
    if (!playbackReleaseTimerRef.current) {
      playbackReleaseTimerRef.current = setTimeout(() => {
        playbackReleaseTimerRef.current = null;
        if (stateRef.current === 'idle') setAudioPlaybackActive(false);
      }, PLAYBACK_RELEASE_MS);
    }
  }, [audioPlaybackActive, outputLevel, state]);

  useEffect(() => () => {
    if (playbackReleaseTimerRef.current) clearTimeout(playbackReleaseTimerRef.current);
  }, []);

  const Avatar = mode === 'video' ? RobotAvatarVideo : RobotAvatarSprite;
  const visualState = audioPlaybackActive && (state === 'speaking' || state === 'idle')
    ? 'speaking'
    : (state === 'speaking' ? 'idle' : state);
  return <Avatar {...props} state={visualState} outputLevel={outputLevel} />;
}
