import { useEffect, useState } from 'react';
import RobotAvatarSprite from './RobotAvatarSprite';
import RobotAvatarVideo from './RobotAvatarVideo';

const FALLBACK_MODE = 'sprite';
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

  useEffect(() => {
    let active = true;
    loadAvatarMode().then(nextMode => {
      if (active) setMode(nextMode);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const onAudioPlaybackStart = () => setAudioPlaybackActive(true);
    window.addEventListener('xz:audio-playback-start', onAudioPlaybackStart);
    return () => window.removeEventListener('xz:audio-playback-start', onAudioPlaybackStart);
  }, []);

  useEffect(() => {
    if (state !== 'speaking') setAudioPlaybackActive(false);
  }, [state]);

  const Avatar = mode === 'video' ? RobotAvatarVideo : RobotAvatarSprite;
  const visualState = audioPlaybackActive
    ? 'speaking'
    : (state === 'speaking' ? 'idle' : state);
  return <Avatar {...props} state={visualState} outputLevel={outputLevel} />;
}
