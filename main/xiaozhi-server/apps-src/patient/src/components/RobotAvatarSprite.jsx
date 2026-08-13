import { useEffect, useState } from 'react';
import { C } from '../theme';

const STATE_CONFIG = {
  idle: { className: 'robot-avatar--idle', glow: C.mist, accent: C.amber },
  listening: { className: 'robot-avatar--listening', glow: C.amber, accent: C.sage },
  thinking: { className: 'robot-avatar--thinking', glow: C.mist, accent: C.sage },
  speaking: { className: 'robot-avatar--speaking', glow: C.amber, accent: C.sage },
};

const SPRITE_ROOT = `${import.meta.env.BASE_URL}panda-sprite`;

const GESTURES_BY_STATE = {
  idle: ['tilt-left', 'wave-left', 'tilt-right', 'wave-right', 'nod', 'open-arms'],
  listening: ['lean-in', 'nod', 'tilt-left', 'wave-right', 'tilt-right'],
  thinking: ['tilt-left', 'slow-nod', 'tilt-right', 'lean-in'],
  speaking: ['talk-left', 'wave-right', 'talk-right', 'wave-left', 'nod', 'open-arms'],
};

const GESTURE_TIMING = {
  idle: [2300, 4200],
  listening: [1600, 3000],
  thinking: [2000, 3400],
  speaking: [1400, 2700],
};

const GESTURE_DURATION = {
  greet: 1800,
  'tilt-left': 1500,
  'tilt-right': 1500,
  nod: 1050,
  'slow-nod': 1700,
  'wave-left': 1500,
  'wave-right': 1500,
  'open-arms': 1500,
  'lean-in': 1200,
  'talk-left': 1200,
  'talk-right': 1200,
};

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

export default function RobotAvatarSprite({ state = 'idle', outputLevel = 0 }) {
  const [blink, setBlink] = useState('none');
  const [gesture, setGesture] = useState('rest');
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;
  const voice = Math.max(0, Math.min(1, Number(outputLevel) || 0));
  const mouthOpen = state === 'speaking' ? Math.min(1, 0.12 + voice * 0.98) : 0;

  useEffect(() => {
    if (typeof window === 'undefined' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return undefined;
    }

    const timers = new Set();
    let firstBlink = true;
    let cancelled = false;

    const later = (callback, delay) => {
      const timer = window.setTimeout(() => {
        timers.delete(timer);
        callback();
      }, delay);
      timers.add(timer);
      return timer;
    };

    const scheduleBlink = () => {
      const wait = firstBlink ? randomBetween(1200, 2400) : randomBetween(2800, 6800);
      firstBlink = false;
      later(() => {
        if (cancelled) return;
        const doubleBlink = Math.random() < 0.22;
        setBlink('closed');
        later(() => {
          if (cancelled) return;
          setBlink('none');
          if (!doubleBlink) {
            scheduleBlink();
            return;
          }
          later(() => {
            if (cancelled) return;
            setBlink('closed');
            later(() => {
              if (cancelled) return;
              setBlink('none');
              scheduleBlink();
            }, 115);
          }, 135);
        }, 125);
      }, wait);
    };

    scheduleBlink();
    return () => {
      cancelled = true;
      timers.forEach(timer => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return undefined;
    }

    const timers = new Set();
    let cancelled = false;
    let firstGesture = true;
    const pool = GESTURES_BY_STATE[state] || GESTURES_BY_STATE.idle;
    const [minimumDelay, maximumDelay] = GESTURE_TIMING[state] || GESTURE_TIMING.idle;
    let gestureCursor = Math.floor(Math.random() * pool.length);

    const later = (callback, delay) => {
      const timer = window.setTimeout(() => {
        timers.delete(timer);
        callback();
      }, delay);
      timers.add(timer);
      return timer;
    };

    const scheduleGesture = () => {
      const wait = firstGesture ? randomBetween(650, 1050) : randomBetween(minimumDelay, maximumDelay);
      later(() => {
        if (cancelled) return;
        const nextGesture = firstGesture ? 'greet' : pool[gestureCursor % pool.length];
        firstGesture = false;
        gestureCursor += 1;
        setGesture(nextGesture);
        later(() => {
          if (cancelled) return;
          setGesture('rest');
          scheduleGesture();
        }, GESTURE_DURATION[nextGesture]);
      }, wait);
    };

    setGesture('rest');
    scheduleGesture();
    return () => {
      cancelled = true;
      timers.forEach(timer => window.clearTimeout(timer));
      timers.clear();
    };
  }, [state]);

  const motionClasses = [
    blink === 'none' ? '' : `robot-avatar--blink-${blink}`,
    gesture === 'rest' ? '' : `robot-avatar--gesture-${gesture}`,
  ].filter(Boolean).join(' ');

  return (
    <div
      className={`robot-avatar robot-avatar--sprite ${config.className} ${motionClasses}`}
      style={{
        '--robot-glow': config.glow,
        '--robot-accent': config.accent,
        '--mouth-open': mouthOpen,
        '--mouth-width': `${20 + mouthOpen * 9}px`,
        '--mouth-height': `${3 + mouthOpen * 15}px`,
        '--mouth-opacity': Math.min(1, mouthOpen * 3),
        '--mouth-border-alpha': mouthOpen * 0.9,
      }}
      role="img"
      aria-label="熊猫陪伴机器人安安"
    >
      <div className="robot-avatar__halo" />
      <div className="robot-avatar__orbit robot-avatar__orbit--outer" />
      <div className="robot-avatar__orbit robot-avatar__orbit--inner" />

      <div className="robot-avatar__figure" aria-hidden="true">
        <span className="robot-avatar__neck-joint" />
        <div className="robot-avatar__body">
          <img
            className="robot-avatar__body-image"
            src={`${SPRITE_ROOT}/panda-body-v3.png`}
            alt=""
            draggable="false"
          />
        </div>

        <img
          className="robot-avatar__arm robot-avatar__arm--left"
          src={`${SPRITE_ROOT}/panda-arm-left-v3.png`}
          alt=""
          draggable="false"
        />
        <img
          className="robot-avatar__arm robot-avatar__arm--right"
          src={`${SPRITE_ROOT}/panda-arm-right-v3.png`}
          alt=""
          draggable="false"
        />

        <div className="robot-avatar__head">
          <img
            className="robot-avatar__head-image"
            src={`${SPRITE_ROOT}/panda-head-v4.png`}
            alt=""
            draggable="false"
          />
          <span className="robot-avatar__eyelid robot-avatar__eyelid--left" />
          <span className="robot-avatar__eyelid robot-avatar__eyelid--right" />
          <span className="robot-avatar__mouth-live" />
        </div>

        <div className="robot-avatar__shadow" />
      </div>
    </div>
  );
}
