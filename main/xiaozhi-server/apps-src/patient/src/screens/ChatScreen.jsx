import { useRef } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import RobotAvatar from '../components/RobotAvatar';
import WaveBars from '../components/WaveBars';
import voiceRoomBackground from '../assets/voice/voice-room.webp';
import { getReplyDensity } from '../utils/replyText';

const FALLBACK_COPY = {
  offline: '语音服务正在连接，请稍等一会儿。',
  standby: '我在这里，想聊天时叫一声“小暖”。',
  ready: '我一直在呢，您直接说话就好。',
};

export default function ChatScreen({
  aiState,
  msg,
  lastHeard,
  connected,
  recording,
  userSpeaking,
  inputLevel = 0,
  outputLevel = 0,
  ordinaryVoiceAwake = true,
  onOpenSettings,
  onOpenAssistantTools,
}) {
  const pressTimerRef = useRef(null);
  const longPressTriggeredRef = useRef(false);
  const standby = !ordinaryVoiceAwake;
  const displayState = standby
    ? 'idle'
    : (aiState === 'idle' && connected && recording && userSpeaking ? 'listening' : aiState);
  const fallback = !connected
    ? FALLBACK_COPY.offline
    : standby
      ? FALLBACK_COPY.standby
      : FALLBACK_COPY.ready;
  const activitySource = userSpeaking || aiState !== 'speaking' ? 'input' : 'output';
  const activityLevel = activitySource === 'input' ? inputLevel : outputLevel;
  const replyText = msg || fallback;
  const replyDensity = getReplyDensity(replyText);

  const clearPressTimer = () => {
    if (!pressTimerRef.current) return;
    clearTimeout(pressTimerRef.current);
    pressTimerRef.current = null;
  };

  const beginSettingsPress = () => {
    longPressTriggeredRef.current = false;
    clearPressTimer();
    pressTimerRef.current = setTimeout(() => {
      longPressTriggeredRef.current = true;
      pressTimerRef.current = null;
      onOpenAssistantTools?.();
    }, 1200);
  };

  const endSettingsPress = () => {
    clearPressTimer();
    if (longPressTriggeredRef.current) {
      longPressTriggeredRef.current = false;
      return;
    }
    onOpenSettings?.();
  };

  return (
    <div
      className={`voice-screen voice-screen--${displayState} voice-screen--reply-${replyDensity}`}
      style={{ '--voice-room-background': `url(${voiceRoomBackground})` }}
    >
      <button
        className="voice-screen__settings"
        type="button"
        onPointerDown={beginSettingsPress}
        onPointerUp={endSettingsPress}
        onPointerLeave={clearPressTimer}
        onPointerCancel={clearPressTimer}
        aria-label="打开语音设置"
        title="语音设置"
      >
        <SlidersHorizontal size={20} strokeWidth={1.8} aria-hidden="true" />
        <span>语音设置</span>
      </button>

      <div className="voice-screen__main">
        <div className="voice-screen__avatar" aria-hidden="true">
          <RobotAvatar state={displayState} outputLevel={outputLevel} />
        </div>

        <div className="voice-screen__conversation" aria-live="polite">
          {lastHeard && !standby && (
            <div className="voice-screen__heard">
              <span>您说</span>
              <p>{lastHeard}</p>
            </div>
          )}

          <div className="voice-screen__reply">
            <span>小暖</span>
            <p className={`voice-screen__reply-text voice-screen__reply-text--${replyDensity}${msg ? '' : ' voice-screen__reply--quiet'}`}>
              {replyText}
            </p>
          </div>
        </div>
      </div>

      <div className="voice-screen__activity" aria-hidden="true">
        <WaveBars
          source={activitySource}
          level={activityLevel}
          active={connected && (recording || aiState === 'speaking')}
        />
      </div>
    </div>
  );
}
