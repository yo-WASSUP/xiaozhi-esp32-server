import { useEffect, useMemo, useRef, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID } from '../constants';

export default function LegacyVideoScreen() {
  const [document, setDocument] = useState('');
  const [assets, setAssets] = useState([]);
  const [storyboard, setStoryboard] = useState([]);
  const [task, setTask] = useState(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState('');
  const fileRef = useRef(null);

  const selectedCount = useMemo(() => assets.filter(item => item.selected).length, [assets]);

  useEffect(() => {
    loadRecentMedia();
  }, []);

  const toast = (message) => {
    setFlash(message);
    setTimeout(() => setFlash(''), 2400);
  };

  const loadRecentMedia = async () => {
    try {
      const r = await fetch(`/api/hospice/messages?device_id=${encodeURIComponent(DEVICE_ID)}&limit=120`);
      const list = await r.json();
      const media = (Array.isArray(list) ? list : [])
        .filter(item => ['photo', 'video'].includes(item.message_type) && item.file_path)
        .map(item => ({
          url: item.file_path,
          type: item.message_type === 'video' ? 'video' : 'image',
          label: item.content || item.file_path,
          file_name: item.content || '',
          selected: true,
        }));
      setAssets(uniqueAssets(media));
    } catch (err) {
      console.error(err);
      toast('素材加载失败');
    }
  };

  const uploadAsset = async (file) => {
    const fd = new FormData();
    fd.append('file', file, file.name);
    const r = await fetch('/api/hospice/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (!j.success) throw new Error(j.error || '上传失败');
    return {
      url: j.url,
      type: file.type.startsWith('video/') ? 'video' : 'image',
      label: file.name,
      file_name: file.name,
      selected: true,
    };
  };

  const onPickFiles = async (event) => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    setBusy(true);
    try {
      const uploaded = [];
      for (const file of files) {
        if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) continue;
        uploaded.push(await uploadAsset(file));
      }
      setAssets(items => uniqueAssets([...uploaded, ...items]));
    } catch (err) {
      toast(err.message || '上传失败');
    } finally {
      setBusy(false);
    }
  };

  const generateStoryboard = async () => {
    if (!document.trim()) {
      toast('请先粘贴生命文档');
      return;
    }
    setBusy(true);
    setTask(null);
    try {
      const r = await fetch('/api/hospice/video/storyboard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID,
          document,
          assets: assets.filter(item => item.selected),
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '分镜生成失败');
      setStoryboard(j.storyboard || []);
    } catch (err) {
      toast(err.message || '分镜生成失败');
    } finally {
      setBusy(false);
    }
  };

  const renderVideo = async () => {
    if (!storyboard.length) {
      toast('请先生成分镜');
      return;
    }
    setBusy(true);
    try {
      const r = await fetch('/api/hospice/video/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, storyboard }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '视频生成失败');
      setTask(j.task);
    } catch (err) {
      toast(err.message || '视频生成失败');
    } finally {
      setBusy(false);
    }
  };

  const updateScene = (index, patch) => {
    setStoryboard(items => items.map((scene, i) => i === index ? { ...scene, ...patch } : scene));
  };

  const toggleAsset = (url) => {
    setAssets(items => items.map(item => item.url === url ? { ...item, selected: !item.selected } : item));
  };

  return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, overflow: 'auto', padding: '44px 16px 18px', animation: 'fadeUp .4s ease' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
        <div>
          <div style={titleStyle}>生命回顾影像</div>
          <div style={subStyle}>用真实照片和视频生成可下载的回顾短片</div>
        </div>
        <button onClick={() => fileRef.current?.click()} disabled={busy} style={buttonStyle(false)}>上传素材</button>
      </div>

      <section style={sectionStyle}>
        <div style={sectionTitleStyle}>生命文档</div>
        <textarea
          value={document}
          onChange={e => setDocument(e.target.value)}
          placeholder="把已确认的生命文档粘贴到这里"
          style={documentStyle}
        />
      </section>

      <section style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <div>
            <div style={sectionTitleStyle}>素材</div>
            <div style={subStyle}>已选 {selectedCount} 个素材。可从消息记录自动读取，也可以继续上传。</div>
          </div>
          <button onClick={loadRecentMedia} disabled={busy} style={buttonStyle(false)}>刷新</button>
        </div>
        <div style={assetGridStyle}>
          {assets.length === 0 ? (
            <div style={emptyStyle}>还没有照片或视频素材。</div>
          ) : assets.map(asset => (
            <button key={asset.url} onClick={() => toggleAsset(asset.url)} style={assetStyle(asset.selected)}>
              <div style={{ fontSize: 20 }}>{asset.type === 'video' ? '🎬' : '🖼️'}</div>
              <div style={{ minWidth: 0, textAlign: 'left' }}>
                <div style={{ fontSize: 12, color: C.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{asset.label}</div>
                <div style={{ fontSize: 11, color: C.inkFaint }}>{asset.selected ? '已选' : '未选'}</div>
              </div>
            </button>
          ))}
        </div>
      </section>

      <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
        <button onClick={generateStoryboard} disabled={busy} style={buttonStyle(true)}>{busy ? '处理中' : '生成分镜'}</button>
        <button onClick={renderVideo} disabled={busy || !storyboard.length} style={buttonStyle(false)}>生成视频</button>
      </div>

      {storyboard.length > 0 && (
        <section style={sectionStyle}>
          <div style={sectionTitleStyle}>分镜</div>
          <div style={{ display: 'grid', gap: 10 }}>
            {storyboard.map((scene, index) => (
              <div key={`${scene.title}-${index}`} style={sceneStyle}>
                <input value={scene.title || ''} onChange={e => updateScene(index, { title: e.target.value })} style={inputStyle} />
                <textarea value={scene.text || ''} onChange={e => updateScene(index, { text: e.target.value })} rows={3} style={sceneTextStyle} />
                <select value={scene.media_url || ''} onChange={e => {
                  const asset = assets.find(item => item.url === e.target.value);
                  updateScene(index, { media_url: e.target.value, media_type: asset?.type || '' });
                }} style={inputStyle}>
                  <option value="">无素材，使用纯色页</option>
                  {assets.filter(item => item.selected).map(asset => <option key={asset.url} value={asset.url}>{asset.label}</option>)}
                </select>
              </div>
            ))}
          </div>
        </section>
      )}

      {task?.status === 'ready' && (
        <section style={sectionStyle}>
          <div style={sectionTitleStyle}>视频已生成</div>
          <video src={task.output_url} controls style={{ width: '100%', borderRadius: 8, background: '#111', marginTop: 8 }} />
          <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
            <a href={task.output_url} download style={linkStyle}>下载 MP4</a>
            {task.subtitle_url && <a href={task.subtitle_url} download style={linkStyle}>下载字幕</a>}
          </div>
        </section>
      )}

      {flash && <div style={toastStyle}>{flash}</div>}
      <input ref={fileRef} type="file" accept="image/*,video/*" multiple onChange={onPickFiles} style={{ display: 'none' }} />
    </div>
  );
}

function uniqueAssets(items) {
  const seen = new Set();
  const result = [];
  for (const item of items) {
    if (!item.url || seen.has(item.url)) continue;
    seen.add(item.url);
    result.push(item);
  }
  return result;
}

const titleStyle = { fontSize: 20, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em' };
const subStyle = { fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginTop: 3 };
const sectionStyle = { border: `1px solid ${C.mist}22`, borderRadius: 8, background: C.card, padding: 12, marginBottom: 12 };
const sectionTitleStyle = { fontSize: 14, color: C.ink, fontFamily: 'Noto Serif SC,serif', marginBottom: 8 };
const sectionHeaderStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 8 };
const documentStyle = { width: '100%', minHeight: 150, boxSizing: 'border-box', resize: 'vertical', border: `1px solid ${C.mist}33`, borderRadius: 8, padding: 10, color: C.ink, fontFamily: 'Noto Sans SC', lineHeight: 1.6, outline: 'none' };
const assetGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8 };
const assetStyle = (selected) => ({ display: 'grid', gridTemplateColumns: '24px 1fr', alignItems: 'center', gap: 8, border: `1px solid ${selected ? C.amber : C.mist}55`, borderRadius: 8, background: selected ? `${C.amber}18` : 'rgba(255,250,242,.62)', padding: 8, cursor: 'pointer', minWidth: 0 });
const sceneStyle = { display: 'grid', gap: 8, border: `1px solid ${C.mist}22`, borderRadius: 8, padding: 10, background: 'rgba(255,250,242,.58)' };
const inputStyle = { width: '100%', boxSizing: 'border-box', border: `1px solid ${C.mist}33`, borderRadius: 6, padding: '8px 9px', color: C.ink, fontFamily: 'Noto Sans SC', outline: 'none' };
const sceneTextStyle = { ...inputStyle, resize: 'vertical', lineHeight: 1.5 };
const emptyStyle = { color: C.inkFaint, fontSize: 13, padding: '14px 0', textAlign: 'center' };
const buttonStyle = (primary) => ({ border: `1px solid ${primary ? C.amber : C.mist}66`, background: primary ? `${C.amber}24` : 'rgba(255,250,242,.72)', color: primary ? C.ink : C.inkMid, borderRadius: 8, height: 36, padding: '0 13px', cursor: 'pointer', fontFamily: 'Noto Sans SC', whiteSpace: 'nowrap' });
const linkStyle = { display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 12px', borderRadius: 8, border: `1px solid ${C.amber}66`, color: C.ink, background: `${C.amber}20`, textDecoration: 'none', fontSize: 13 };
const toastStyle = { position: 'fixed', bottom: 92, left: '50%', transform: 'translateX(-50%)', background: C.ink, color: '#fff', borderRadius: 14, padding: '8px 14px', fontSize: 13, zIndex: 100 };

