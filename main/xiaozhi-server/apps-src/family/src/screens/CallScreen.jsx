import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID, SENDER_NAME } from '../constants';
import Card from '../components/Card';

export default function CallScreen() {
  const [callState, setCallState] = useState('idle'); // idle | calling | connecting | active
  const [callType, setCallType] = useState('video');
  const [secs, setSecs] = useState(0);
  const [muted, setMuted] = useState(false);
  const [camOff, setCamOff] = useState(false);
  const [localStream, setLocalStream] = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);
  const [flash, setFlash] = useState('');

  const clientRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const localVideoRef = useRef(null);

  useEffect(() => {
    const client = new window.CallClient({
      deviceId: DEVICE_ID,
      role: 'family',
      onState: (s) => {
        if (s === 'calling' || s === 'connecting' || s === 'active') setCallState(s);
        else if (s === 'idle') setCallState('idle');
      },
      onLocalStream: setLocalStream,
      onRemoteStream: setRemoteStream,
      onAccepted: () => { /* 对端接听 - 等连接建好 */ },
      onRejected: (reason) => {
        setFlash(reason === 'busy' ? '⚠ 对方正忙' : '对方拒绝了');
        setTimeout(() => setFlash(''), 2500);
      },
      onEnded: (reason) => {
        setLocalStream(null); setRemoteStream(null);
        setSecs(0); setMuted(false); setCamOff(false);
        if (reason === 'peer-absent') {
          setFlash('⚠ 对方不在线');
          setTimeout(() => setFlash(''), 2500);
        }
      },
    });
    clientRef.current = client;
    client.connect();
    return () => {
      try {
        client.hangup();
        if (typeof client.disconnect === 'function') client.disconnect();
      } catch (_) { }
    };
  }, []);

  // 同时依赖 callState：localStream 在 placeCall 时就拿到了，
  // 但此时 callState='calling'，<video> 元素还没挂载。
  // 当 callState 跳到 'connecting'/'active'，active 视图渲染、ref 才有效，
  // effect 必须再跑一次才能把 srcObject 赋上去。
  useEffect(() => {
    if (remoteVideoRef.current && remoteStream) remoteVideoRef.current.srcObject = remoteStream;
    if (remoteAudioRef.current && remoteStream) remoteAudioRef.current.srcObject = remoteStream;
  }, [remoteStream, callState]);

  useEffect(() => {
    if (localVideoRef.current && localStream) localVideoRef.current.srcObject = localStream;
  }, [localStream, callState]);

  useEffect(() => {
    if (callState !== 'active') return;
    const id = setInterval(() => setSecs(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [callState]);

  const fmt = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;

  const dial = async (nextCallType) => {
    setCallType(nextCallType);
    setSecs(0);
    try {
      await clientRef.current.placeCall({ callType: nextCallType, fromName: SENDER_NAME });
    } catch (e) {
      setFlash('⚠ 无法使用摄像头/麦克风: ' + e.message);
      setTimeout(() => setFlash(''), 3000);
    }
  };
  const hangup = () => { clientRef.current && clientRef.current.hangup(); };
  const doMute = () => { const v = !muted; setMuted(v); clientRef.current && clientRef.current.toggleMute(v); };
  const doCam = () => { const v = !camOff; setCamOff(v); clientRef.current && clientRef.current.toggleCamera(v); };

  if (callState === 'idle') return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, overflow: 'auto', padding: '52px 16px 24px', animation: 'fadeUp .4s ease' }}>
      <div style={{ fontSize: 22, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em', marginBottom: 4 }}>联系父亲</div>
      <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginBottom: 24 }}>小暖会协助父亲接听通话</div>

      <Card style={{ padding: '18px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 54, height: 54, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${C.amber}cc,#b87340aa)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26 }}>👴</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 17, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 400, marginBottom: 3 }}>父亲</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: C.sage, boxShadow: `0 0 6px ${C.sage}` }} />
            <span style={{ fontSize: 13, color: C.sage, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>在线 · 正在休息</span>
          </div>
        </div>
        <div style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>平板在线</div>
      </Card>

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {[
          ['video', '视频通话', '📹', C.amber],
          ['voice', '语音通话', '📞', C.sage],
        ].map(([t, l, ic, cl]) => (
          <button key={t} onClick={() => dial(t)} style={{ flex: 1, padding: '20px 12px', borderRadius: 20, border: `1.5px solid ${cl}66`, background: `${cl}14`, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, transition: 'all .2s', boxShadow: `0 4px 18px ${cl}22` }}>
            <span style={{ fontSize: 32 }}>{ic}</span>
            <span style={{ fontSize: 15, color: cl, fontFamily: 'Noto Sans SC', fontWeight: 400 }}>{l}</span>
          </button>
        ))}
      </div>

      {flash && <div style={{ marginTop: 12, padding: '8px 14px', borderRadius: 10, background: flash.startsWith('⚠') ? `${C.red}22` : `${C.sage}22`, fontSize: 13, color: flash.startsWith('⚠') ? C.red : C.sage, fontFamily: 'Noto Sans SC', fontWeight: 300, textAlign: 'center' }}>{flash}</div>}
    </div>
  );

  if (callState === 'calling') return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, background: `radial-gradient(circle at 50% 40%,#1a2a18,#080e08)`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 28, animation: 'fadeIn .4s ease' }}>
      <div style={{ position: 'relative', width: 160, height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ position: 'absolute', inset: -(i * 22), borderRadius: '50%', border: `1.5px solid ${C.sage}${['44', '2a', '18'][i]}`, animation: `ripple ${1.6 + i * .4}s ease-out ${i * .35}s infinite`, pointerEvents: 'none' }} />
        ))}
        <div style={{ width: 100, height: 100, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${C.amber}cc,#b87340aa)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 44 }}>👴</div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 26, color: 'rgba(255,255,255,.88)', fontFamily: 'Noto Serif SC,serif', fontWeight: 300, marginBottom: 6 }}>正在呼叫父亲…</div>
        <div style={{ fontSize: 14, color: 'rgba(255,255,255,.4)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>等待对方接听</div>
      </div>
      <button onClick={hangup} style={{ width: 70, height: 70, borderRadius: '50%', background: '#c0484a', border: 'none', cursor: 'pointer', fontSize: 28, marginTop: 16, boxShadow: '0 4px 20px rgba(192,72,74,.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>📵</button>
    </div>
  );

  // active / connecting
  return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, background: `radial-gradient(circle at 50% 40%,#1a2a18,#080e08)`, display: 'flex', flexDirection: 'column', animation: 'fadeIn .4s ease' }}>
      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {callType === 'video' ? (
          <video ref={remoteVideoRef} autoPlay playsInline
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', background: '#000' }} />
        ) : (
          <>
            <audio ref={remoteAudioRef} autoPlay />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 72, marginBottom: 12, opacity: .55 }}>👴</div>
              <div style={{ fontSize: 16, color: 'rgba(255,255,255,.4)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
                {callState === 'connecting' ? '正在接通…' : '语音通话中'}
              </div>
            </div>
          </>
        )}
        <div style={{ position: 'absolute', top: 20, left: 0, right: 0, textAlign: 'center', zIndex: 2 }}>
          <div style={{ fontSize: 20, color: 'rgba(255,255,255,.88)', fontFamily: 'Noto Serif SC,serif', fontWeight: 300, marginBottom: 4, textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>父亲</div>
          <div style={{ fontSize: 14, color: 'rgba(255,255,255,.55)', fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.1em', textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>
            {callState === 'connecting' ? '接通中…' : fmt(secs)}
          </div>
        </div>
        {callType === 'video' && (
          <div style={{ position: 'absolute', top: 20, right: 16, width: 110, height: 150, borderRadius: 12, background: '#1a2218', border: '1px solid rgba(255,255,255,.12)', overflow: 'hidden', zIndex: 2, boxShadow: '0 4px 18px rgba(0,0,0,.5)' }}>
            <video ref={localVideoRef} autoPlay playsInline muted
              style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000', opacity: camOff ? 0 : 1 }} />
            {camOff && <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: 'rgba(255,255,255,.4)' }}>📵</div>}
          </div>
        )}
      </div>

      <div style={{ padding: '16px 32px 20px', display: 'flex', justifyContent: 'space-around', alignItems: 'center', background: 'rgba(0,0,0,.3)' }}>
        {[
          { icon: muted ? '🔇' : '🎤', label: muted ? '已静音' : '静音', act: doMute, on: muted },
          { icon: camOff ? '📵' : '📹', label: camOff ? '摄像头关' : '摄像头', act: doCam, on: camOff, hide: callType !== 'video' },
        ].filter(b => !b.hide).map((b, i) => (
          <button key={i} onClick={b.act} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: b.on ? 'rgba(255,255,255,.22)' : 'rgba(255,255,255,.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>
              {b.icon}
            </div>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,.45)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>{b.label}</span>
          </button>
        ))}
        <button onClick={hangup} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
          <div style={{ width: 52, height: 52, borderRadius: '50%', background: '#c0484acc', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, boxShadow: '0 3px 14px rgba(192,72,74,.5)' }}>📵</div>
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,.45)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>挂断</span>
        </button>
      </div>
    </div>
  );
}
