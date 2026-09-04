import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import pandaIdleVideo from '../../panda-video/panda-7793-idle.webm';
import pandaListeningVideo from '../../panda-video/panda-7793-listening.webm';
import pandaSpeakingVideo from '../../panda-video/panda-7793-speaking.webm';
import pandaPoster from '../../panda-video/panda-7793-poster.png';
import { createVideoHandoff } from './videoHandoff';

const STATE_CONFIG = {
  idle: { className: 'robot-avatar--idle', glow: C.mist, accent: C.amber },
  listening: { className: 'robot-avatar--listening', glow: C.amber, accent: C.sage },
  thinking: { className: 'robot-avatar--thinking', glow: C.mist, accent: C.sage },
  speaking: { className: 'robot-avatar--speaking', glow: C.amber, accent: C.sage },
};

const VIDEO_BY_STATE = {
  idle: 'idle',
  listening: 'listening',
  thinking: 'idle',
  speaking: 'speaking',
};

const VIDEO_LAYERS = [
  { action: 'idle', src: pandaIdleVideo },
  { action: 'listening', src: pandaListeningVideo },
  { action: 'speaking', src: pandaSpeakingVideo },
];

const FIRST_FRAME_TIMEOUT_MS = 1000;
const VIDEO_FADE_MS = 140;

function videoStateFor(state) {
  return VIDEO_BY_STATE[state] || 'idle';
}

function waitForLoadedData(video) {
  if (video.readyState >= 2) return Promise.resolve();
  return new Promise(resolve => {
    let timer = null;
    const finish = () => {
      if (timer) window.clearTimeout(timer);
      video.removeEventListener('loadeddata', finish);
      video.removeEventListener('error', finish);
      resolve();
    };
    video.addEventListener('loadeddata', finish);
    video.addEventListener('error', finish);
    timer = window.setTimeout(finish, FIRST_FRAME_TIMEOUT_MS);
  });
}

function waitForPaintedFrame(video) {
  if (typeof video.requestVideoFrameCallback !== 'function') {
    return new Promise(resolve => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
    });
  }
  return new Promise(resolve => {
    let settled = false;
    let timer = null;
    const finish = () => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      resolve();
    };
    video.requestVideoFrameCallback(finish);
    timer = window.setTimeout(finish, FIRST_FRAME_TIMEOUT_MS);
  });
}

async function prepareVideo(video, reduceMotion) {
  await waitForLoadedData(video);
  if (reduceMotion) return;
  try {
    await video.play();
  } catch (_) {
    // Muted inline video normally autoplays; the poster remains visible if WebView refuses.
  }
  await waitForPaintedFrame(video);
}

export default function RobotAvatarVideo({ state = 'idle' }) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;
  const requestedVideoState = videoStateFor(state);
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const initialVideoStateRef = useRef(requestedVideoState);
  const videoRefs = useRef(new Map());
  const pauseTimersRef = useRef(new Set());
  const activeVideoStateRef = useRef(initialVideoStateRef.current);
  const [activeVideoState, setActiveVideoState] = useState(initialVideoStateRef.current);
  const handoffRef = useRef(null);

  if (!handoffRef.current) {
    handoffRef.current = createVideoHandoff(
      initialVideoStateRef.current,
      (nextState, previousState) => {
        activeVideoStateRef.current = nextState;
        setActiveVideoState(nextState);
        const timer = window.setTimeout(() => {
          pauseTimersRef.current.delete(timer);
          if (activeVideoStateRef.current !== previousState) {
            videoRefs.current.get(previousState)?.pause();
          }
        }, VIDEO_FADE_MS + 60);
        pauseTimersRef.current.add(timer);
      },
    );
  }

  useEffect(() => {
    const target = videoRefs.current.get(requestedVideoState);
    if (!target) return undefined;
    handoffRef.current.request(
      requestedVideoState,
      () => prepareVideo(target, reduceMotion),
    );
    return undefined;
  }, [reduceMotion, requestedVideoState]);

  useEffect(() => {
    const initialVideo = videoRefs.current.get(initialVideoStateRef.current);
    if (initialVideo && !reduceMotion) {
      initialVideo.play().catch(() => {});
    }
    return () => {
      handoffRef.current?.cancel();
      pauseTimersRef.current.forEach(timer => window.clearTimeout(timer));
      pauseTimersRef.current.clear();
      videoRefs.current.forEach(video => video.pause());
    };
  }, [reduceMotion]);

  return (
    <div
      className={`robot-avatar robot-avatar--video ${config.className}`}
      style={{
        '--robot-glow': config.glow,
        '--robot-accent': config.accent,
      }}
      role="img"
      aria-label="熊猫陪伴机器人安安"
    >
      <div className="robot-avatar__halo" />
      <div className="robot-avatar__orbit robot-avatar__orbit--outer" />
      <div className="robot-avatar__orbit robot-avatar__orbit--inner" />

      <div className="robot-avatar__figure robot-avatar__figure--video" aria-hidden="true">
        <img
          className="robot-avatar__video-poster"
          src={pandaPoster}
          alt=""
        />
        {VIDEO_LAYERS.map(video => (
          <video
            key={video.action}
            ref={node => {
              if (node) videoRefs.current.set(video.action, node);
              else videoRefs.current.delete(video.action);
            }}
            className={`robot-avatar__video${activeVideoState === video.action ? ' is-active' : ''}`}
            src={video.src}
            data-action={video.action}
            autoPlay={video.action === initialVideoStateRef.current && !reduceMotion}
            muted
            loop
            playsInline
            preload="auto"
          />
        ))}
      </div>
    </div>
  );
}
