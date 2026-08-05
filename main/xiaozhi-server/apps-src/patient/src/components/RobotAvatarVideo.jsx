import { C } from '../theme';
import pandaIdleVideo from '../../panda-video/panda-9267-idle.webm';
import pandaWaveVideo from '../../panda-video/panda-9267-wave.webm';
import pandaSpeakingVideo from '../../panda-video/panda-9267-speaking.webm';
import pandaPoster from '../../panda-video/panda-9267-poster.png';

const STATE_CONFIG = {
  idle: { className: 'robot-avatar--idle', glow: C.mist, accent: C.amber },
  listening: { className: 'robot-avatar--listening', glow: C.amber, accent: C.sage },
  thinking: { className: 'robot-avatar--thinking', glow: C.mist, accent: C.sage },
  speaking: { className: 'robot-avatar--speaking', glow: C.amber, accent: C.sage },
};

const VIDEO_BY_STATE = {
  idle: { src: pandaIdleVideo, action: 'idle' },
  listening: { src: pandaWaveVideo, action: 'wave' },
  thinking: { src: pandaIdleVideo, action: 'idle' },
  speaking: { src: pandaSpeakingVideo, action: 'speaking' },
};

export default function RobotAvatarVideo({ state = 'idle' }) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;
  const video = VIDEO_BY_STATE[state] || VIDEO_BY_STATE.idle;
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  return (
    <div
      className={`robot-avatar robot-avatar--video ${config.className}`}
      style={{
        '--robot-glow': config.glow,
        '--robot-accent': config.accent,
      }}
      role="img"
      aria-label="熊猫陪伴机器人小暖"
    >
      <div className="robot-avatar__halo" />
      <div className="robot-avatar__orbit robot-avatar__orbit--outer" />
      <div className="robot-avatar__orbit robot-avatar__orbit--inner" />

      <div className="robot-avatar__figure robot-avatar__figure--video" aria-hidden="true">
        <video
          key={video.src}
          className="robot-avatar__video"
          src={video.src}
          poster={pandaPoster}
          data-action={video.action}
          autoPlay={!reduceMotion}
          muted
          loop
          playsInline
          preload="auto"
        />
      </div>
    </div>
  );
}
