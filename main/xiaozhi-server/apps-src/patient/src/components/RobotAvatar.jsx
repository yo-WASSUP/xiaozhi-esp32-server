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

export default function RobotAvatar(props) {
  const [mode, setMode] = useState(cachedMode || FALLBACK_MODE);

  useEffect(() => {
    let active = true;
    loadAvatarMode().then(nextMode => {
      if (active) setMode(nextMode);
    });
    return () => { active = false; };
  }, []);

  const Avatar = mode === 'video' ? RobotAvatarVideo : RobotAvatarSprite;
  return <Avatar {...props} />;
}
