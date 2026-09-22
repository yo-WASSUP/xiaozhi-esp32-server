import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import pandaIdleVideo from '../../panda-video/panda-7793-idle.webm';
import pandaListeningVideo from '../../panda-video/panda-7793-listening.webm';
import pandaSpeakingVideo from '../../panda-video/panda-7793-speaking.webm';
import pandaPoster from '../../panda-video/panda-7793-poster.png';
import { createVideoHandoff, getVideoLayers } from './videoHandoff';

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

const VIDEO_SOURCE_BY_ACTION = {
  idle: pandaIdleVideo,
  listening: pandaListeningVideo,
  speaking: pandaSpeakingVideo,
};

const FIRST_FRAME_TIMEOUT_MS = 1000;

function videoStateFor(state) {
  return VIDEO_BY_STATE[state] || 'idle';
}

function waitForLoadedData(video) {
  if (video.readyState >= 2) return Promise.resolve();
  return new Promise((resolve, reject) => {
    let timer = null;
    const cleanup = () => {
      if (timer) window.clearTimeout(timer);
      video.removeEventListener('loadeddata', handleLoaded);
      video.removeEventListener('error', handleError);
    };
    const handleLoaded = () => {
      cleanup();
      resolve();
    };
    const handleError = () => {
      cleanup();
      reject(video.error || new Error('video loading failed'));
    };
    video.addEventListener('loadeddata', handleLoaded);
    video.addEventListener('error', handleError);
    timer = window.setTimeout(() => {
      cleanup();
      reject(new Error('video loading timed out'));
    }, FIRST_FRAME_TIMEOUT_MS);
  });
}

function waitForPaintedFrame(video) {
  if (typeof video.requestVideoFrameCallback !== 'function') {
    return new Promise(resolve => {
      window.requestAnimationFrame(() => window.requestAnimationFrame(resolve));
    });
  }
  return new Promise((resolve, reject) => {
    let settled = false;
    let timer = null;
    let callbackId = null;
    const finish = (error = null) => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      if (error) reject(error);
      else resolve();
    };
    callbackId = video.requestVideoFrameCallback(() => finish());
    timer = window.setTimeout(() => {
      if (typeof video.cancelVideoFrameCallback === 'function' && callbackId !== null) {
        video.cancelVideoFrameCallback(callbackId);
      }
      finish(new Error('video first frame timed out'));
    }, FIRST_FRAME_TIMEOUT_MS);
  });
}

async function prepareVideo(video, reduceMotion) {
  await waitForLoadedData(video);
  if (reduceMotion) return;
  await video.play();
  await waitForPaintedFrame(video);
}

function reportPlaybackError(action, error) {
  console.warn('[avatar-video] playback failed', {
    action,
    error: error?.message || String(error),
    name: error?.name || 'Error',
    userAgent: navigator.userAgent,
  });
}

export default function RobotAvatarVideo({ state = 'idle' }) {
  const config = STATE_CONFIG[state] || STATE_CONFIG.idle;
  const requestedVideoState = videoStateFor(state);
  const reduceMotion = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const initialVideoStateRef = useRef(requestedVideoState);
  const videoRefs = useRef(new Map());
  const activeVideoStateRef = useRef(initialVideoStateRef.current);
  const [activeVideoState, setActiveVideoState] = useState(initialVideoStateRef.current);
  const [activeVideoReady, setActiveVideoReady] = useState(false);
  const handoffRef = useRef(null);

  if (!handoffRef.current) {
    handoffRef.current = createVideoHandoff(
      initialVideoStateRef.current,
      (nextState, previousState) => {
        videoRefs.current.get(previousState)?.pause();
        activeVideoStateRef.current = nextState;
        setActiveVideoState(nextState);
        setActiveVideoReady(true);
      },
    );
  }

  useEffect(() => {
    if (requestedVideoState === activeVideoStateRef.current) {
      handoffRef.current.request(requestedVideoState, () => Promise.resolve());
      return undefined;
    }
    const target = videoRefs.current.get(requestedVideoState);
    if (!target) return undefined;
    handoffRef.current.request(
      requestedVideoState,
      () => prepareVideo(target, reduceMotion),
    ).catch(error => reportPlaybackError(requestedVideoState, error));
    return undefined;
  }, [reduceMotion, requestedVideoState]);

  useEffect(() => {
    let mounted = true;
    const initialVideo = videoRefs.current.get(initialVideoStateRef.current);
    if (initialVideo) {
      prepareVideo(initialVideo, reduceMotion)
        .then(() => {
          if (mounted) setActiveVideoReady(true);
        })
        .catch(error => reportPlaybackError(initialVideoStateRef.current, error));
    }
    return () => {
      mounted = false;
      handoffRef.current?.cancel();
      videoRefs.current.forEach(video => video.pause());
    };
  }, [reduceMotion]);

  const videoLayers = getVideoLayers(
    activeVideoState,
    requestedVideoState,
    activeVideoReady,
  );

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
        {videoLayers.map(video => (
          <video
            key={video.state}
            ref={node => {
              if (node) videoRefs.current.set(video.state, node);
              else videoRefs.current.delete(video.state);
            }}
            className={`robot-avatar__video is-${video.role}`}
            src={VIDEO_SOURCE_BY_ACTION[video.state]}
            data-action={video.state}
            controls={false}
            disablePictureInPicture
            disableRemotePlayback
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
