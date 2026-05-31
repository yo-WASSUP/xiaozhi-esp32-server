import { useEffect, useRef, useState } from 'react';
import { DEVICE_ID } from '../constants';
import { C } from '../theme';

const SAMPLE_TEXT = '今天天气还不错，我出去走了一小会儿。你在家慢慢休息，想喝水就喊我一声。晚一点我再给你发消息。';
const DIALECT_INSTRUCTION = '请用四川话，亲切自然，语速稍慢，像家人在身边陪伴一样说话。';
const MIN_RECORD_SECONDS = 8;
const TARGET_RECORD_SECONDS = 20;
const SUPPORTED_AUDIO_EXTS = new Set(['wav', 'mp3', 'ogg', 'm4a', 'aac', 'pcm']);

const audioBufferToWav = (buffer) => {
  const channels = buffer.numberOfChannels;
  const length = buffer.length * channels * 2;
  const view = new DataView(new ArrayBuffer(44 + length));
  const writeString = (offset, value) => {
    for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
  };
  let offset = 0;
  writeString(offset, 'RIFF'); offset += 4;
  view.setUint32(offset, 36 + length, true); offset += 4;
  writeString(offset, 'WAVE'); offset += 4;
  writeString(offset, 'fmt '); offset += 4;
  view.setUint32(offset, 16, true); offset += 4;
  view.setUint16(offset, 1, true); offset += 2;
  view.setUint16(offset, channels, true); offset += 2;
  view.setUint32(offset, buffer.sampleRate, true); offset += 4;
  view.setUint32(offset, buffer.sampleRate * channels * 2, true); offset += 4;
  view.setUint16(offset, channels * 2, true); offset += 2;
  view.setUint16(offset, 16, true); offset += 2;
  writeString(offset, 'data'); offset += 4;
  view.setUint32(offset, length, true); offset += 4;

  const channelData = [];
  for (let c = 0; c < channels; c += 1) channelData.push(buffer.getChannelData(c));
  for (let i = 0; i < buffer.length; i += 1) {
    for (let c = 0; c < channels; c += 1) {
      const s = Math.max(-1, Math.min(1, channelData[c][i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([view], { type: 'audio/wav' });
};

const toWavBlob = async (recordedBlob) => {
  const arrayBuffer = await recordedBlob.arrayBuffer();
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return recordedBlob;
  const ctx = new AudioContext();
  try {
    const decoded = await ctx.decodeAudioData(arrayBuffer.slice(0));
    return audioBufferToWav(decoded);
  } finally {
    try { await ctx.close(); } catch (_) { /* noop */ }
  }
};

const normalizeUploadedAudio = async (file) => {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (SUPPORTED_AUDIO_EXTS.has(ext)) {
    return { blob: file, ext };
  }
  const wavBlob = await toWavBlob(file);
  return { blob: wavBlob, ext: 'wav' };
};

const formatSeconds = (seconds) => {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = Math.floor(seconds % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
};

const statusLabel = (status) => ({
  DEPLOYING: '生成中',
  OK: '可用',
  UNDEPLOYED: '未完成',
  FAILED: '失败',
  Failed: '失败',
  UNKNOWN: '未知',
}[status] || status || '未提交');

const statusTone = (status, active) => {
  if (active) return C.green;
  if (status === 'OK') return C.sage;
  if (status === 'DEPLOYING') return C.amber;
  if (status === 'FAILED' || status === 'Failed') return C.red;
  return C.inkFaint;
};

const voiceKey = (voice) => voice?.voice_id || voice?.speaker_id || '';

export default function SettingsPanel({ open, onClose }) {
  const [configured, setConfigured] = useState(false);
  const [missingConfig, setMissingConfig] = useState([]);
  const [maxSampleMb, setMaxSampleMb] = useState(10);
  const [model, setModel] = useState('cosyvoice-v3.5-flash');
  const [voiceId, setVoiceId] = useState('');
  const [alias, setAlias] = useState('家属声音');
  const [settings, setSettings] = useState({});
  const [voices, setVoices] = useState([]);
  const [recording, setRecording] = useState(false);
  const [recordSeconds, setRecordSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [blob, setBlob] = useState(null);
  const [sourceName, setSourceName] = useState('');
  const [sourceKind, setSourceKind] = useState('');
  const [sourceExt, setSourceExt] = useState('wav');
  const [previewUrl, setPreviewUrl] = useState('');
  const [busy, setBusy] = useState('');
  const [tip, setTip] = useState('');
  const [pairingCode, setPairingCode] = useState('');
  const [pairingExpiresAt, setPairingExpiresAt] = useState(0);
  const [families, setFamilies] = useState([]);

  const recorderRef = useRef(null);
  const fileInputRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const analyserRef = useRef(null);
  const audioCtxRef = useRef(null);
  const rafRef = useRef(null);
  const durationRef = useRef(0);

  const applySettings = (nextSettings = {}) => {
    setSettings(nextSettings);
    setVoices(Array.isArray(nextSettings.voices) ? nextSettings.voices : []);
    setVoiceId(nextSettings.voice_id || nextSettings.speaker_id || '');
    setAlias(nextSettings.alias || '家属声音');
    setModel(nextSettings.model || model);
  };

  const loadConfig = async () => {
    try {
      const r = await fetch(`/api/hospice/voice-clone/config?device_id=${encodeURIComponent(DEVICE_ID)}`);
      const j = await r.json();
      setConfigured(!!j.configured);
      setMissingConfig(j.missing_config || []);
      setMaxSampleMb(j.max_sample_mb || 10);
      setModel(j.model || j.settings?.model || 'cosyvoice-v3.5-flash');
      applySettings(j.settings || {});
    } catch (e) {
      setTip(`加载失败：${e?.message || '未知错误'}`);
    }
  };

  const loadFamilies = async () => {
    try {
      const r = await fetch(`/api/hospice/pairing/families?device_id=${encodeURIComponent(DEVICE_ID)}`);
      const j = await r.json();
      setFamilies(Array.isArray(j.families) ? j.families : []);
    } catch (_) {
      setFamilies([]);
    }
  };

  const createPairingCode = async () => {
    setBusy('pairing');
    setTip('');
    try {
      const r = await fetch('/api/hospice/pairing/code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '生成配对码失败');
      setPairingCode(j.code || '');
      setPairingExpiresAt(j.expires_at || 0);
      setTip('配对码已生成，请让家属端输入。');
    } catch (e) {
      setTip(`生成配对码失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  useEffect(() => {
    if (open) {
      loadConfig();
      loadFamilies();
    }
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      clearInterval(timerRef.current);
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      audioCtxRef.current?.close?.().catch?.(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const updateLevel = () => {
    const analyser = analyserRef.current;
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    setLevel(Math.min(1, Math.sqrt(sum / data.length) * 5));
    rafRef.current = requestAnimationFrame(updateLevel);
  };

  const stopTracks = async () => {
    clearInterval(timerRef.current);
    cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    analyserRef.current = null;
    if (audioCtxRef.current) {
      try { await audioCtxRef.current.close(); } catch (_) { /* noop */ }
      audioCtxRef.current = null;
    }
  };

  const resetCurrentSample = () => {
    setBlob(null);
    setSourceName('');
    setSourceKind('');
    setSourceExt('wav');
    setRecordSeconds(0);
    durationRef.current = 0;
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return '';
    });
  };

  const startRecord = async () => {
    setTip('');
    resetCurrentSample();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        const ctx = new AudioContext();
        audioCtxRef.current = ctx;
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        analyserRef.current = analyser;
        rafRef.current = requestAnimationFrame(updateLevel);
      }
      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : undefined,
      });
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        setRecording(false);
        setLevel(0);
        stopTracks();
        const audioBlob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        setTip('正在整理录音...');
        toWavBlob(audioBlob).then((wavBlob) => {
          setBlob(wavBlob);
          setSourceName(`录音 ${formatSeconds(durationRef.current)}`);
          setSourceKind('record');
          setSourceExt('wav');
          setPreviewUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return URL.createObjectURL(wavBlob);
          });
          setTip(`录好了，时长 ${formatSeconds(durationRef.current)}。可以先试听。`);
        }).catch(() => {
          setBlob(audioBlob);
          setSourceName(`录音 ${formatSeconds(durationRef.current)}`);
          setSourceKind('record');
          setSourceExt('wav');
          setPreviewUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return URL.createObjectURL(audioBlob);
          });
          setTip(`录好了，时长 ${formatSeconds(durationRef.current)}。可以先试听。`);
        });
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      timerRef.current = setInterval(() => {
        durationRef.current += 1;
        setRecordSeconds(durationRef.current);
      }, 1000);
      setSourceKind('recording');
      setTip('正在录音，请自然朗读。');
    } catch (e) {
      setTip('无法录音，请允许麦克风权限。');
    }
  };

  const stopRecord = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    } else {
      stopTracks();
      setRecording(false);
    }
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const uploadLocalFile = async (file) => {
    if (!file) return;
    setBusy('upload');
    setTip('');
    try {
      resetCurrentSample();
      const normalized = await normalizeUploadedAudio(file);
      setBlob(normalized.blob);
      setSourceName(file.name || '本地音频');
      setSourceKind('upload');
      setSourceExt(normalized.ext || 'wav');
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        const ctx = new AudioContext();
        try {
          const decoded = await ctx.decodeAudioData(await normalized.blob.arrayBuffer());
          durationRef.current = Math.max(1, Math.floor(decoded.duration));
          setRecordSeconds(durationRef.current);
        } finally {
          try { await ctx.close(); } catch (_) { /* noop */ }
        }
      }
      setPreviewUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return URL.createObjectURL(normalized.blob);
      });
      setTip('文件已载入，可以试听后提交。');
    } catch (e) {
      setTip(`文件读取失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const submitClone = async () => {
    if (!configured) {
      setTip(`配置未完成：${missingConfig.join('、') || '缺少配置'}`);
      return;
    }
    if (!blob) {
      setTip('请先录一段声音，或者上传本地录音文件。');
      return;
    }
    if (durationRef.current < MIN_RECORD_SECONDS) {
      setTip(`录音太短，至少 ${MIN_RECORD_SECONDS} 秒。`);
      return;
    }
    setBusy('submit');
    setTip('正在提交...');
    try {
      const fd = new FormData();
      fd.append('device_id', DEVICE_ID);
      fd.append('alias', alias.trim() || '家属声音');
      fd.append('language', 'zh');
      fd.append('enable_preprocess', 'true');
      fd.append('file', blob, `cosyvoice-${Date.now()}.${sourceExt || 'wav'}`);
      const r = await fetch('/api/hospice/voice-clone/train', { method: 'POST', body: fd });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '提交失败');
      applySettings(j.settings || {});
      setTip('已提交。稍后点“查状态”。');
    } catch (e) {
      setTip(`提交失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const queryStatus = async (id = voiceId) => {
    const targetId = id.trim();
    if (!targetId) {
      setTip('请先选择一个声音。');
      return;
    }
    setBusy(`query:${targetId}`);
    setTip('正在查询...');
    try {
      const q = new URLSearchParams({ device_id: DEVICE_ID, voice_id: targetId });
      const r = await fetch(`/api/hospice/voice-clone/status?${q.toString()}`);
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '查询失败');
      applySettings(j.settings || {});
      setVoiceId(targetId);
      setTip(`状态：${statusLabel(j.settings?.status)}`);
    } catch (e) {
      setTip(`查询失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const refreshVoices = async () => {
    setBusy('refresh');
    setTip('正在刷新...');
    try {
      const q = new URLSearchParams({ device_id: DEVICE_ID, page_size: '50' });
      const r = await fetch(`/api/hospice/voice-clone/list?${q.toString()}`);
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '刷新失败');
      applySettings(j.settings || {});
      setTip('已刷新。');
    } catch (e) {
      setTip(`刷新失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const deleteVoice = async (voice) => {
    const id = voiceKey(voice);
    if (!id) return;
    if (!window.confirm(`删除“${voice.alias || '家属声音'}”？会同时删除阿里云音色和本地记录，删除后不能恢复。`)) return;
    setBusy(`delete:${id}`);
    setTip('正在删除云端音色...');
    try {
      const q = new URLSearchParams({ device_id: DEVICE_ID, voice_id: id });
      const r = await fetch(`/api/hospice/voice-clone/delete?${q.toString()}`, { method: 'DELETE' });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '删除失败');
      applySettings(j.settings || {});
      if (voiceId === id) setVoiceId(j.settings?.voice_id || '');
      setTip(j.remote_deleted ? '已删除云端音色和本地记录。' : '已删除本地记录。');
    } catch (e) {
      setTip(`删除失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const activateVoice = async (voice = null) => {
    const id = voiceKey(voice) || voiceId.trim();
    if (!id) {
      setTip('请先选择一个声音。');
      return;
    }
    if (voice?.status && voice.status !== 'OK' && !voice.active) {
      setTip(`这个声音还不可用：${statusLabel(voice.status)}`);
      return;
    }
    setBusy(`activate:${id}`);
    setTip('正在启用...');
    try {
      const r = await fetch('/api/hospice/voice-clone/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID,
          voice_id: id,
          model: voice?.model || settings.model || model,
          alias: voice?.alias || alias.trim() || '家属声音',
          instruction: DIALECT_INSTRUCTION,
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '启用失败');
      applySettings(j.settings || {});
      setVoiceId(id);
      setTip('已启用。重新连接后生效。');
    } catch (e) {
      setTip(`启用失败：${e?.message || '未知错误'}`);
    } finally {
      setBusy('');
    }
  };

  const chooseVoice = (voice) => {
    setVoiceId(voiceKey(voice));
    setAlias(voice.alias || '家属声音');
    setSettings((prev) => ({ ...prev, ...voice }));
    setTip('');
  };

  const buttonStyle = (kind = 'normal', compact = false, disabled = false) => ({
    border: 'none',
    borderRadius: 10,
    padding: compact ? '8px 10px' : '10px 14px',
    background: disabled ? `${C.mist}26` : kind === 'primary' ? C.sage : kind === 'danger' ? C.red : `${C.mist}22`,
    color: disabled ? C.inkFaint : kind === 'primary' || kind === 'danger' ? 'white' : C.inkMid,
    cursor: busy || disabled ? 'not-allowed' : 'pointer',
    fontSize: compact ? 13 : 14,
    fontFamily: 'Noto Sans SC',
    opacity: busy || disabled ? 0.72 : 1,
  });

  const sectionStyle = {
    border: `1px solid ${C.mist}22`,
    borderRadius: 8,
    padding: 14,
    background: 'rgba(255,255,255,.62)',
    marginBottom: 14,
  };

  const warn = tip.includes('失败') || tip.includes('缺少') || tip.includes('未完成') || tip.includes('无法') || tip.includes('不可用');
  const currentStatus = settings.active ? '已启用' : statusLabel(settings.status);
  const sampleTooShort = !!blob && durationRef.current < MIN_RECORD_SECONDS;
  const canSubmit = configured && !!blob && !sampleTooShort && !recording && !busy;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(30,24,16,.35)', backdropFilter: 'blur(6px)', display: 'flex', justifyContent: 'flex-end' }}>
      <style>{`
        @keyframes voicePulse {
          0%, 100% { transform: scale(.72); opacity: .45; }
          50% { transform: scale(1); opacity: 1; }
        }
      `}</style>
      <div style={{ width: 520, maxWidth: '94vw', height: '100%', background: '#fffaf2', boxShadow: '-10px 0 32px rgba(30,24,16,.18)', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.mist}22`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 22, color: C.ink, fontFamily: 'Noto Serif SC,serif' }}>声音设置</div>
            <div style={{ fontSize: 12, color: statusTone(settings.status, settings.active), marginTop: 4, fontFamily: 'Noto Sans SC' }}>{currentStatus}</div>
          </div>
          <button onClick={onClose} style={{ ...buttonStyle(), width: 38, height: 38, borderRadius: '50%', padding: 0, fontSize: 20 }}>×</button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 22, fontFamily: 'Noto Sans SC', color: C.inkMid }}>
          {!configured && (
            <div style={{ ...sectionStyle, color: C.red, fontSize: 13 }}>配置未完成：{missingConfig.join('、')}</div>
          )}

          <div style={sectionStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 17, color: C.ink }}>家属配对</div>
                <div style={{ fontSize: 12, color: C.inkFaint, marginTop: 3 }}>生成一次性配对码，让家属端绑定这位患者。</div>
              </div>
              <button disabled={!!busy} onClick={createPairingCode} style={buttonStyle('primary', true)}>
                {busy === 'pairing' ? '生成中...' : '生成配对码'}
              </button>
            </div>
            {pairingCode && (
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: 12, borderRadius: 8, background: `${C.sage}12`, marginBottom: 10 }}>
                <div style={{ fontSize: 34, letterSpacing: '.18em', color: C.ink, fontFamily: 'Noto Sans SC', fontVariantNumeric: 'tabular-nums' }}>{pairingCode}</div>
                <div style={{ fontSize: 12, color: C.inkFaint }}>10 分钟内有效{pairingExpiresAt ? `，到期时间 ${new Date(pairingExpiresAt * 1000).toLocaleTimeString()}` : ''}</div>
              </div>
            )}
            <div style={{ fontSize: 13, color: C.inkFaint, lineHeight: 1.7 }}>
              {families.length === 0 ? '还没有绑定家属。' : `已绑定：${families.map(item => item.family_name).join('、')}`}
            </div>
          </div>

          <div style={sectionStyle}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 10 }}>
              <div style={{ fontSize: 17, color: C.ink }}>声音克隆</div>
              <div style={{ fontSize: 12, color: C.inkFaint }}>录音或上传一段家属声音</div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="audio/*"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                uploadLocalFile(file);
              }}
            />
            <input
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder="声音名称"
              style={{ width: '100%', boxSizing: 'border-box', padding: '11px 12px', borderRadius: 10, border: `1px solid ${C.mist}33`, marginBottom: 12, fontSize: 15, outline: 'none' }}
            />
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
              <button disabled={!!busy || recording} onClick={startRecord} style={buttonStyle('primary', false, !!busy || recording)}>{recording ? '录音中' : '开始录音'}</button>
              <button disabled={!!busy || recording} onClick={openFilePicker} style={buttonStyle('normal', false, !!busy || recording)}>上传本地文件</button>
            </div>
            <div style={{ padding: 12, borderRadius: 8, background: `${C.mist}12`, marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: C.inkFaint, marginBottom: 6 }}>照着读</div>
              <div style={{ fontSize: 16, color: C.inkMid, lineHeight: 1.7 }}>{SAMPLE_TEXT}</div>
            </div>

            {recording && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, padding: '8px 10px', borderRadius: 8, background: `${C.red}0f` }}>
                <button onClick={stopRecord} style={buttonStyle('danger', true)}>停止</button>
                <div style={{ fontVariantNumeric: 'tabular-nums', color: C.red, minWidth: 42 }}>{formatSeconds(recordSeconds)}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, height: 20 }}>
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      style={{
                        width: 7 + level * 8,
                        height: 7 + level * 8,
                        borderRadius: '50%',
                        background: C.sage,
                        animation: `voicePulse ${0.7 + i * 0.12}s ease-in-out infinite`,
                        animationDelay: `${i * 0.08}s`,
                      }}
                    />
                  ))}
                </div>
                <div style={{ marginLeft: 'auto', fontSize: 12, color: C.inkFaint }}>建议 {TARGET_RECORD_SECONDS} 秒</div>
              </div>
            )}

            {sourceName && (
              <div style={{ fontSize: 12, color: C.inkFaint, marginBottom: 8 }}>
                当前声音：{sourceName}{recordSeconds ? ` · ${formatSeconds(recordSeconds)}` : ''}
                {sampleTooShort ? ` · 至少 ${MIN_RECORD_SECONDS} 秒` : ''}
              </div>
            )}

            {previewUrl && <audio controls src={previewUrl} style={{ width: '100%', marginBottom: 12 }} />}
            <button disabled={!canSubmit} onClick={submitClone} style={buttonStyle('primary', false, !canSubmit)}>
              {busy === 'submit' ? '提交中...' : blob ? '提交复刻' : '先录音或上传'}
            </button>
            <span style={{ marginLeft: 10, fontSize: 12, color: C.inkFaint }}>最多 {maxSampleMb}MB</span>
          </div>

          <div style={sectionStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <div style={{ fontSize: 16, color: C.ink, flex: 1 }}>已有声音</div>
              <button disabled={!!busy} onClick={refreshVoices} style={buttonStyle('normal', true)}>
                {busy === 'refresh' ? '刷新中' : '刷新'}
              </button>
            </div>
            {voices.length === 0 ? (
              <div style={{ fontSize: 13, color: C.inkFaint }}>还没有保存的声音。</div>
            ) : voices.map((voice) => {
              const id = voiceKey(voice);
              const selected = id === voiceId;
              return (
                <div
                  key={id}
                  onClick={() => chooseVoice(voice)}
                  style={{
                    border: `1px solid ${selected ? C.sage : `${C.mist}22`}`,
                    borderRadius: 8,
                    padding: 12,
                    background: selected ? `${C.sage}10` : 'rgba(255,255,255,.5)',
                    marginBottom: 10,
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ fontSize: 15, color: C.ink, flex: 1 }}>{voice.alias || '家属声音'}</div>
                    <div style={{ fontSize: 12, color: statusTone(voice.status, voice.active) }}>{voice.active ? '使用中' : statusLabel(voice.status)}</div>
                  </div>
                  <div style={{ fontSize: 12, color: C.inkFaint, marginTop: 4 }}>
                    {voice.updated_at || '刚刚'}{selected ? ' · 已选择' : ''}
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                    <button
                      disabled={!!busy}
                      onClick={(e) => { e.stopPropagation(); queryStatus(id); }}
                      style={buttonStyle('normal', true)}
                    >
                      {busy === `query:${id}` ? '查询中' : '查状态'}
                    </button>
                    <button
                      disabled={!!busy || voice.active}
                      onClick={(e) => { e.stopPropagation(); activateVoice(voice); }}
                      style={buttonStyle('primary', true)}
                    >
                      {voice.active ? '已启用' : busy === `activate:${id}` ? '启用中' : '启用'}
                    </button>
                    <button
                      disabled={!!busy}
                      onClick={(e) => { e.stopPropagation(); deleteVoice(voice); }}
                      style={buttonStyle('danger', true)}
                    >
                      {busy === `delete:${id}` ? '删除中' : '删除'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ fontSize: 13, lineHeight: 1.8, color: C.inkFaint }}>
            启用后，小暖会用这个声音说四川话。{settings.resource_link && <a href={settings.resource_link} target="_blank" rel="noreferrer" style={{ color: C.sage, marginLeft: 8 }}>试听样音</a>}
            {tip && <div style={{ marginTop: 8, color: warn ? C.red : C.inkMid }}>{tip}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
