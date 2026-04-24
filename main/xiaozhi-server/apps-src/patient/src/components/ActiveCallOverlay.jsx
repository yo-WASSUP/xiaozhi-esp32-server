import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';

export default function ActiveCallOverlay({ caller, callType, onEnd, localStream, remoteStream, onToggleMute, onToggleCamera }) {
  const [secs, setSecs] = useState(0);
  const [muted, setMuted] = useState(false);
  const [camOff, setCamOff] = useState(false);

  const remoteVideoRef = useRef(null);
  const localVideoRef = useRef(null);
  const remoteAudioRef = useRef(null);

  useEffect(() => { const id = setInterval(() => setSecs(s => s + 1), 1000); return () => clearInterval(id); }, []);

  useEffect(() => {
    if (remoteVideoRef.current && remoteStream) remoteVideoRef.current.srcObject = remoteStream;
    if (remoteAudioRef.current && remoteStream) remoteAudioRef.current.srcObject = remoteStream;
  }, [remoteStream]);

  useEffect(() => {
    if (localVideoRef.current && localStream) localVideoRef.current.srcObject = localStream;
  }, [localStream]);

  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const doMute = () => { const v = !muted; setMuted(v); onToggleMute && onToggleMute(v); };
  const doCam = () => { const v = !camOff; setCamOff(v); onToggleCamera && onToggleCamera(v); };

  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 100, background: '#0a0806', display: 'flex', animation: 'fadeIn .5s ease' }}>
      {/* remote video / audio */}
      <div style={{ flex: 1, position: 'relative', background: 'radial-gradient(ellipse at center,#1a2218 0%,#0a0c08 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {callType === 'video' ? (
          <video ref={remoteVideoRef} autoPlay playsInline
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', background: '#000' }} />
        ) : (
          <>
            <audio ref={remoteAudioRef} autoPlay />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 88, marginBottom: 16, opacity: .6 }}>{caller.avatar}</div>
              <div style={{ fontSize: 22, color: 'rgba(255,255,255,.5)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>语音通话中</div>
            </div>
          </>
        )}

        {/* caller name + timer */}
        <div style={{ position: 'absolute', top: 36, left: 40, animation: 'fadeIn .6s ease', zIndex: 2 }}>
          <div style={{ fontSize: 26, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, color: 'rgba(255,255,255,.9)', marginBottom: 4, textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>
            {caller.from}
          </div>
          <div style={{ fontSize: 16, color: 'rgba(255,255,255,.55)', fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.14em', textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>
            {fmt(secs)}
          </div>
        </div>

        {/* self preview */}
        {callType === 'video' && (
          <div style={{ position: 'absolute', top: 36, right: 36, width: 180, height: 130, borderRadius: 16, background: '#1a2218', border: '1.5px solid rgba(255,255,255,.12)', overflow: 'hidden', boxShadow: '0 4px 24px rgba(0,0,0,.5)', zIndex: 2 }}>
            <video ref={localVideoRef} autoPlay playsInline muted
              style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000', opacity: camOff ? 0 : 1 }} />
            {camOff && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, color: 'rgba(255,255,255,.4)' }}>📵</div>
            )}
            <div style={{ position: 'absolute', bottom: 6, right: 8, fontSize: 10, color: 'rgba(255,255,255,.55)', fontFamily: 'Noto Sans SC' }}>我</div>
          </div>
        )}
      </div>

      {/* controls sidebar */}
      <div style={{ width: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, background: 'rgba(0,0,0,.35)', padding: '0 0 40px' }}>
        {[
          { icon: muted ? '🔇' : '🎤', label: muted ? '已静音' : '静音', act: doMute, active: muted },
          { icon: camOff ? '📵' : '📹', label: camOff ? '摄像头关' : '摄像头', act: doCam, active: camOff, hide: callType !== 'video' },
        ].filter(b => !b.hide).map((b, i) => (
          <button key={i} onClick={b.act} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: 12, borderRadius: 16, border: 'none', background: b.active ? 'rgba(255,255,255,.18)' : 'rgba(255,255,255,.07)', cursor: 'pointer', width: 80, transition: 'background .2s' }}>
            <span style={{ fontSize: 26 }}>{b.icon}</span>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,.5)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>{b.label}</span>
          </button>
        ))}
        <button onClick={onEnd} style={{ width: 66, height: 66, borderRadius: '50%', background: `${C.red}cc`, border: 'none', cursor: 'pointer', fontSize: 26, marginTop: 12, boxShadow: `0 4px 20px ${C.red}66`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>📵</button>
        <span style={{ fontSize: 11, color: 'rgba(255,255,255,.35)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>挂断</span>
      </div>
    </div>
  );
}
