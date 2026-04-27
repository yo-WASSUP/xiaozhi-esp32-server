import { useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from './constants';
import PaperBg from './components/PaperBg';
import TopBar from './components/TopBar';
import ConnectBar from './components/ConnectBar';
import ChatScreen from './screens/ChatScreen';
import InboxScreen from './screens/InboxScreen';
import IncomingCallOverlay from './components/IncomingCallOverlay';
import ActiveCallOverlay from './components/ActiveCallOverlay';

export default function App() {
  const [screen, setScreen]       = useState('chat');
  const [aiState, setAiState]     = useState('idle');
  const [msg, setMsg]             = useState(null);
  const [incoming, setIncoming]   = useState(null);   // {caller, callType}
  const [inCall, setInCall]       = useState(null);
  const [connected, setConnected] = useState(false);
  const [connectStatus, setConnectStatus] = useState('');
  const [recording, setRecording] = useState(false);
  const [micOk, setMicOk]         = useState(false);
  const [contacts, setContacts]   = useState([]);
  const [eventTick, setEventTick] = useState(0);
  const [maxUploadMb, setMaxUploadMb] = useState(50);

  // 拉一次配置（上传上限）
  useEffect(() => {
    fetch('/api/hospice/config')
      .then(r => r.json())
      .then(j => { if (j && j.upload_max_mb) setMaxUploadMb(j.upload_max_mb); })
      .catch(() => { });
  }, []);

  const unread = contacts.reduce((s, c) => s + (c.unread || 0), 0);

  const loadContacts = async () => {
    try {
      const r = await fetch(`/api/hospice/contacts?device_id=${encodeURIComponent(DEVICE_ID)}`);
      const list = await r.json();
      setContacts(Array.isArray(list) ? list : []);
    } catch (e) { console.error('加载联系人失败', e); }
  };

  // 联系人列表 + SSE 订阅
  useEffect(() => {
    loadContacts();
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    const bump = () => { loadContacts(); setEventTick(t => t + 1); };
    es.addEventListener('message.new', bump);
    es.addEventListener('message.read', bump);
    es.onerror = () => { /* 浏览器自动重连 */ };
    return () => es.close();
  }, []);

  // 桥接 XiaozhiClient 事件（connection / state / llm / stt / ready）
  useEffect(() => {
    const onConn  = e => setConnected(!!e.detail.connected);
    const onState = e => setAiState(e.detail.state);
    const onLlm   = e => setMsg(e.detail.text);
    const onStt   = () => { };
    const onErr   = e => setConnectStatus(e.detail?.message || e.detail?.error?.message || '连接模块初始化失败');
    const onReady = async () => {
      try {
        const ok = await window.XiaozhiClient.init();
        setMicOk(!!ok);
      } catch (err) { console.error('XiaozhiClient init 失败', err); }
    };
    window.addEventListener('xz:connection', onConn);
    window.addEventListener('xz:state', onState);
    window.addEventListener('xz:llm', onLlm);
    window.addEventListener('xz:stt', onStt);
    window.addEventListener('xz:error', onErr);
    window.addEventListener('xz:ready', onReady);
    if (window.XiaozhiClient) onReady();
    return () => {
      window.removeEventListener('xz:connection', onConn);
      window.removeEventListener('xz:state', onState);
      window.removeEventListener('xz:llm', onLlm);
      window.removeEventListener('xz:stt', onStt);
      window.removeEventListener('xz:error', onErr);
      window.removeEventListener('xz:ready', onReady);
    };
  }, []);

  const handleConnect = async () => {
    setConnectStatus('正在连接...');
    try {
      if (!window.XiaozhiClient) {
        setConnectStatus('连接模块还没有加载完成，请刷新页面后重试');
        return;
      }
      const ok = await Promise.race([
        window.XiaozhiClient.connect(),
        new Promise((_, reject) => setTimeout(() => reject(new Error('CONNECT_TIMEOUT')), 10000)),
      ]);
      setConnectStatus(ok ? '' : 'CONNECT_FAILED: check OTA/WSS/8000');
    }
    catch (err) {
      console.error('connect failed', err);
      setConnectStatus(err?.message === 'CONNECT_TIMEOUT' ? 'CONNECT_TIMEOUT: OTA or WSS did not respond in 10s' : (err?.message || 'CONNECT_FAILED'));
    }
  };
  const handleDisconnect = () => window.XiaozhiClient.disconnect();
  const handleSendText   = (t) => window.XiaozhiClient.sendText(t);
  const handleToggleRec  = async () => {
    if (recording) { window.XiaozhiClient.stopRecording(); setRecording(false); return; }
    try {
      await window.XiaozhiClient.startRecording();
      setRecording(true);
    } catch (err) { console.error('开始录音失败', err); setRecording(false); }
  };

  // ── 通话（WebRTC） ──
  const callRef = useRef(null);
  const [localStream, setLocalStream]   = useState(null);
  const [remoteStream, setRemoteStream] = useState(null);

  useEffect(() => {
    const client = new window.CallClient({
      deviceId: DEVICE_ID,
      role: 'patient',
      onIncoming: ({ fromName, callType }) => {
        setIncoming({
          caller: { from: fromName || '家人', avatar: '👤' },
          callType,
        });
      },
      onLocalStream:  (s) => setLocalStream(s),
      onRemoteStream: (s) => setRemoteStream(s),
      onState: (s) => {
        // 状态 connecting / active 时：把来电浮层切换为通话浮层
        if (s === 'connecting' || s === 'active') {
          setIncoming(prev => {
            if (prev) {
              setInCall({ caller: prev.caller, callType: prev.callType });
              return null;
            }
            return null;
          });
        }
      },
      onEnded: () => {
        setIncoming(null);
        setInCall(null);
        setLocalStream(null);
        setRemoteStream(null);
      },
    });
    callRef.current = client;
    client.connect();
    return () => {
      try {
        client.hangup();
        if (typeof client.disconnect === 'function') client.disconnect();
      } catch (_) { }
    };
  }, []);

  const acceptCall  = () => callRef.current && callRef.current.accept();
  const declineCall = () => { callRef.current && callRef.current.reject(); setIncoming(null); };
  const endCall     = () => callRef.current && callRef.current.hangup();
  const toggleMute   = (v) => callRef.current && callRef.current.toggleMute(v);
  const toggleCamera = (v) => callRef.current && callRef.current.toggleCamera(v);

  return (
    <PaperBg>
      <TopBar screen={screen} setScreen={setScreen} unread={unread} />
      {screen === 'chat' && (
        <ConnectBar
          connected={connected} onConnect={handleConnect} onDisconnect={handleDisconnect}
          onSendText={handleSendText} recording={recording} onToggleRec={handleToggleRec} micOk={micOk}
          connectStatus={connectStatus}
        />
      )}

      {screen === 'chat'  && <ChatScreen aiState={aiState} msg={msg} />}
      {screen === 'inbox' && (
        <InboxScreen contacts={contacts} refreshContacts={loadContacts} eventTick={eventTick} maxUploadMb={maxUploadMb} />
      )}

      {incoming && (
        <IncomingCallOverlay caller={incoming.caller} callType={incoming.callType}
          onAccept={acceptCall} onDecline={declineCall} />
      )}
      {inCall && (
        <ActiveCallOverlay caller={inCall.caller} callType={inCall.callType}
          onEnd={endCall}
          localStream={localStream} remoteStream={remoteStream}
          onToggleMute={toggleMute} onToggleCamera={toggleCamera} />
      )}
    </PaperBg>
  );
}
