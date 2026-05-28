import { C } from '../theme';

const STATE_CONFIG = {
  idle: {
    className: 'robot-avatar--idle',
    glow: C.mist,
    eye: C.sage,
    accent: C.amber,
    eyeHeight: 18,
    eyeWidth: 50,
    eyeY: 0,
    pupilScale: 1,
    panelOpacity: .42,
  },
  listening: {
    className: 'robot-avatar--listening',
    glow: C.amber,
    eye: C.amber,
    accent: C.sage,
    eyeHeight: 26,
    eyeWidth: 58,
    eyeY: -1,
    pupilScale: 1.08,
    panelOpacity: .62,
  },
  thinking: {
    className: 'robot-avatar--thinking',
    glow: C.mist,
    eye: C.mist,
    accent: C.sage,
    eyeHeight: 16,
    eyeWidth: 48,
    eyeY: -4,
    pupilScale: .92,
    panelOpacity: .5,
  },
  speaking: {
    className: 'robot-avatar--speaking',
    glow: C.amber,
    eye: C.amber,
    accent: C.sage,
    eyeHeight: 14,
    eyeWidth: 56,
    eyeY: 1,
    pupilScale: 1,
    panelOpacity: .7,
  },
};

function cssVars(config) {
  return {
    '--robot-glow': config.glow,
    '--robot-eye': config.eye,
    '--robot-accent': config.accent,
    '--robot-eye-height': `${config.eyeHeight}px`,
    '--robot-eye-width': `${config.eyeWidth}px`,
    '--robot-eye-y': `${config.eyeY}px`,
    '--robot-pupil-scale': config.pupilScale,
    '--robot-panel-opacity': config.panelOpacity,
  };
}

export default function RobotAvatar({ state = 'idle' }) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;

  return (
    <div className={`robot-avatar ${config.className}`} style={cssVars(config)} aria-hidden="true">
      <div className="robot-avatar__halo" />
      <div className="robot-avatar__head">
        <div className="robot-avatar__antenna">
          <span />
        </div>
        <div className="robot-avatar__face">
          <div className="robot-avatar__shine" />
          <div className="robot-avatar__eyes">
            <div className="robot-avatar__eye robot-avatar__eye--left">
              <span />
            </div>
            <div className="robot-avatar__eye robot-avatar__eye--right">
              <span />
            </div>
          </div>
          <div className="robot-avatar__mouth">
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="robot-avatar__cheek robot-avatar__cheek--left" />
        <div className="robot-avatar__cheek robot-avatar__cheek--right" />
      </div>
      <div className="robot-avatar__neck" />
      <div className="robot-avatar__body">
        <div className="robot-avatar__arm robot-avatar__arm--left" />
        <div className="robot-avatar__torso">
          <div className="robot-avatar__core" />
          <div className="robot-avatar__meter">
            <span />
            <span />
            <span />
          </div>
        </div>
        <div className="robot-avatar__arm robot-avatar__arm--right" />
      </div>
      <div className="robot-avatar__shadow" />
    </div>
  );
}
