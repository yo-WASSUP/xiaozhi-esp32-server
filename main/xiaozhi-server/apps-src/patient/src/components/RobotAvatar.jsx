import { C } from '../theme';

const STATE_CONFIG = {
  idle: {
    className: 'robot-avatar--idle',
    glow: C.mist,
    accent: C.amber,
  },
  listening: {
    className: 'robot-avatar--listening',
    glow: C.amber,
    accent: C.sage,
  },
  thinking: {
    className: 'robot-avatar--thinking',
    glow: C.mist,
    accent: C.sage,
  },
  speaking: {
    className: 'robot-avatar--speaking',
    glow: C.amber,
    accent: C.sage,
  },
};

function cssVars(config) {
  return {
    '--robot-glow': config.glow,
    '--robot-accent': config.accent,
  };
}

export default function RobotAvatar({ state = 'idle' }) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;

  return (
    <div
      className={`robot-avatar ${config.className}`}
      style={cssVars(config)}
      role="img"
      aria-label="熊猫陪伴机器人小暖"
    >
      <div className="robot-avatar__halo" />
      <div className="robot-avatar__orbit robot-avatar__orbit--outer" />
      <div className="robot-avatar__orbit robot-avatar__orbit--inner" />
      <div className="robot-avatar__figure">
        <div className="robot-avatar__head">
          <div className="robot-avatar__ear robot-avatar__ear--left" />
          <div className="robot-avatar__ear robot-avatar__ear--right" />
          <div className="robot-avatar__head-shell">
            <div className="robot-avatar__eye-patch robot-avatar__eye-patch--left">
              <div className="robot-avatar__eye">
                <span />
              </div>
            </div>
            <div className="robot-avatar__eye-patch robot-avatar__eye-patch--right">
              <div className="robot-avatar__eye">
                <span />
              </div>
            </div>
            <div className="robot-avatar__muzzle">
              <div className="robot-avatar__nose" />
              <div className="robot-avatar__mouth">
                <span />
                <span />
              </div>
            </div>
            <div className="robot-avatar__cheek robot-avatar__cheek--left" />
            <div className="robot-avatar__cheek robot-avatar__cheek--right" />
          </div>
        </div>

        <div className="robot-avatar__neck" />
        <div className="robot-avatar__body">
          <div className="robot-avatar__arm robot-avatar__arm--left">
            <span className="robot-avatar__paw" />
          </div>
          <div className="robot-avatar__torso">
            <div className="robot-avatar__torso-shine" />
            <div className="robot-avatar__heart" />
          </div>
          <div className="robot-avatar__arm robot-avatar__arm--right">
            <span className="robot-avatar__paw" />
          </div>
        </div>
      </div>
      <div className="robot-avatar__shadow" />
    </div>
  );
}
