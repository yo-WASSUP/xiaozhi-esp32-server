import { useEffect, useRef, useState } from 'react';
import {
  Microphone,
  MicrophoneSlash,
  Phone,
  PhoneDisconnect,
  User,
  VideoCamera,
  VideoCameraSlash,
  WarningCircle,
} from '@phosphor-icons/react';
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
        setFlash(reason === 'busy' ? '对方正忙' : '对方拒绝了');
        setTimeout(() => setFlash(''), 2500);
      },
      onEnded: (reason) => {
        setLocalStream(null); setRemoteStream(null);
        setSecs(0); setMuted(false); setCamOff(false);
        if (reason === 'peer-absent') {
          setFlash('对方不在线');
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
      setFlash('无法使用摄像头或麦克风：' + e.message);
      setTimeout(() => setFlash(''), 3000);
    }
  };
  const hangup = () => { clientRef.current && clientRef.current.hangup(); };
  const doMute = () => { const v = !muted; setMuted(v); clientRef.current && clientRef.current.toggleMute(v); };
  const doCam = () => { const v = !camOff; setCamOff(v); clientRef.current && clientRef.current.toggleCamera(v); };

  if (callState === 'idle') return (
    <div className="screen" style={{ padding: 'calc(24px + env(safe-area-inset-top)) 16px 24px' }}>
      <div className="screen-title">联系家人</div>
      <div className="screen-subtitle" style={{ marginBottom: 24 }}>小暖会协助家人接听通话</div>

      <Card style={{ padding: '18px', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{ width: 56, height: 56, borderRadius: 16, background: C.primaryContainer, color: C.amber, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><User size={28} weight="duotone" /></div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 17, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 400, marginBottom: 3 }}>家人</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: C.sage, boxShadow: `0 0 6px ${C.sage}` }} />
            <span style={{ fontSize: 13, color: C.sage, fontWeight: 500 }}>在线，正在休息</span>
          </div>
        </div>
        <div style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>平板在线</div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { type: 'video', label: '视频通话', Icon: VideoCamera },
          { type: 'voice', label: '语音通话', Icon: Phone },
        ].map(({ type, label, Icon }) => (
          <button type="button" className="tap-button" key={type} onClick={() => dial(type)} style={{ padding: '20px 12px', borderRadius: 16, border: `1px solid ${C.outline}`, background: '#fff', color: C.amber, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, boxShadow: '0 8px 24px rgba(47,107,85,.06)' }}>
            <span style={{ width: 48, height: 48, borderRadius: 16, background: C.primaryContainer, display: 'grid', placeItems: 'center' }}><Icon size={25} weight="duotone" /></span>
            <span style={{ fontSize: 15, fontWeight: 650 }}>{label}</span>
          </button>
        ))}
      </div>

      {flash && <div role="alert" style={{ marginTop: 12, padding: '11px 14px', borderRadius: 14, background: `${C.red}12`, fontSize: 13, color: C.red, fontWeight: 500, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7 }}><WarningCircle size={18} weight="fill" />{flash}</div>}
    </div>
  );

  if (callState === 'calling') return (
    <div className="screen" style={{ background: 'linear-gradient(180deg,#1a2922,#0d1511)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 28, animation: 'fadeIn .3s ease' }}>
      <div style={{ position: 'relative', width: 160, height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ position: 'absolute', inset: -(i * 22), borderRadius: '50%', border: `1.5px solid ${C.sage}${['44', '2a', '18'][i]}`, animation: `ripple ${1.6 + i * .4}s ease-out ${i * .35}s infinite`, pointerEvents: 'none' }} />
        ))}
        <div style={{ width: 100, height: 100, borderRadius: 28, background: C.primaryContainer, color: C.amber, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><User size={48} weight="duotone" /></div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 26, color: 'rgba(255,255,255,.92)', fontWeight: 650, marginBottom: 6 }}>正在呼叫家人</div>
        <div style={{ fontSize: 14, color: 'rgba(255,255,255,.4)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>等待对方接听</div>
      </div>
      <button type="button" aria-label="取消呼叫" onClick={hangup} style={{ width: 68, height: 68, borderRadius: 22, background: C.red, color: '#fff', border: 'none', cursor: 'pointer', marginTop: 16, boxShadow: '0 8px 24px rgba(179,38,30,.28)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><PhoneDisconnect size={29} weight="fill" /></button>
    </div>
  );

  // active / connecting
  return (
    <div className="screen" style={{ background: 'linear-gradient(180deg,#1a2922,#0d1511)', display: 'flex', flexDirection: 'column', animation: 'fadeIn .3s ease' }}>
      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {callType === 'video' ? (
          <video ref={remoteVideoRef} autoPlay playsInline
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', background: '#000' }} />
        ) : (
          <>
            <audio ref={remoteAudioRef} autoPlay />
            <div style={{ textAlign: 'center' }}>
              <User size={72} color="rgba(255,255,255,.52)" weight="duotone" style={{ marginBottom: 12 }} />
              <div style={{ fontSize: 16, color: 'rgba(255,255,255,.4)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
                {callState === 'connecting' ? '正在接通…' : '语音通话中'}
              </div>
            </div>
          </>
        )}
        <div style={{ position: 'absolute', top: 20, left: 0, right: 0, textAlign: 'center', zIndex: 2 }}>
          <div style={{ fontSize: 20, color: 'rgba(255,255,255,.92)', fontWeight: 650, marginBottom: 4, textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>家人</div>
          <div style={{ fontSize: 14, color: 'rgba(255,255,255,.55)', fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.1em', textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>
            {callState === 'connecting' ? '接通中…' : fmt(secs)}
          </div>
        </div>
        {callType === 'video' && (
          <div style={{ position: 'absolute', top: 20, right: 16, width: 110, height: 150, borderRadius: 12, background: '#1a2218', border: '1px solid rgba(255,255,255,.12)', overflow: 'hidden', zIndex: 2, boxShadow: '0 4px 18px rgba(0,0,0,.5)' }}>
            <video ref={localVideoRef} autoPlay playsInline muted
              style={{ width: '100%', height: '100%', objectFit: 'cover', background: '#000', opacity: camOff ? 0 : 1 }} />
            {camOff && <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,.5)' }}><VideoCameraSlash size={26} /></div>}
          </div>
        )}
      </div>

      <div style={{ padding: '16px 32px 20px', display: 'flex', justifyContent: 'space-around', alignItems: 'center', background: 'rgba(0,0,0,.3)' }}>
        {[
          { Icon: muted ? MicrophoneSlash : Microphone, label: muted ? '已静音' : '静音', act: doMute, on: muted },
          { Icon: camOff ? VideoCameraSlash : VideoCamera, label: camOff ? '摄像头关' : '摄像头', act: doCam, on: camOff, hide: callType !== 'video' },
        ].filter(b => !b.hide).map((b, i) => (
          <button key={i} onClick={b.act} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
            <div style={{ width: 52, height: 52, borderRadius: 17, color: '#fff', background: b.on ? 'rgba(255,255,255,.22)' : 'rgba(255,255,255,.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <b.Icon size={23} weight={b.on ? 'fill' : 'regular'} />
            </div>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,.45)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>{b.label}</span>
          </button>
        ))}
        <button onClick={hangup} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer' }}>
          <div style={{ width: 52, height: 52, borderRadius: 17, background: C.red, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 18px rgba(179,38,30,.3)' }}><PhoneDisconnect size={23} weight="fill" /></div>
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,.45)', fontFamily: 'Noto Sans SC', fontWeight: 300 }}>挂断</span>
        </button>
      </div>
    </div>
  );
}
