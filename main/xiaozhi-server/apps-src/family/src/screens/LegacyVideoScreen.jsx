import { useEffect, useMemo, useRef, useState } from 'react';
import { DEVICE_ID } from '../constants';
import { C } from '../theme';

export default function LegacyVideoScreen() {
  const [document, setDocument] = useState('');
  const [documentStatus, setDocumentStatus] = useState('');
  const [documentUrl, setDocumentUrl] = useState('');
  const [memoryReady, setMemoryReady] = useState(false);
  const [assets, setAssets] = useState([]);
  const [storyboard, setStoryboard] = useState([]);
  const [narrationVoice, setNarrationVoice] = useState('longlaoyi_v3');
  const [task, setTask] = useState(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState('');
  const fileRef = useRef(null);

  const selectedCount = useMemo(() => assets.filter(item => item.selected).length, [assets]);
  const canStoryboard = document.trim() || memoryReady;
  const hasStoryboard = storyboard.length > 0;

  useEffect(() => {
    loadVideoSource();
  }, []);

  const toast = (message) => {
    setFlash(message);
    window.setTimeout(() => setFlash(''), 2400);
  };

  const loadVideoSource = async () => {
    try {
      const r = await fetch(`/api/hospice/video/source?device_id=${encodeURIComponent(DEVICE_ID)}`);
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '来源读取失败');
      setDocument(j.document || '');
      setDocumentStatus(j.document_status || '');
      setDocumentUrl(j.document_url || '');
      setMemoryReady(hasMemory(j.memory));
      setAssets(uniqueAssets((j.assets || []).map(item => ({ ...item, selected: item.selected !== false }))));
    } catch (err) {
      console.error(err);
      toast(err.message || '来源加载失败');
    }
  };

  const uploadAsset = async (file) => {
    const fd = new FormData();
    fd.append('device_id', DEVICE_ID);
    fd.append('file', file, file.name);
    const r = await fetch('/api/hospice/video/assets', { method: 'POST', body: fd });
    const j = await r.json();
    if (!j.success) throw new Error(j.error || '上传失败');
    return j.asset;
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
      toast(`已上传 ${uploaded.length} 个素材`);
    } catch (err) {
      toast(err.message || '上传失败');
    } finally {
      setBusy(false);
    }
  };

  const updateAssetLocal = (url, patch) => {
    setAssets(items => items.map(item => item.url === url ? { ...item, ...patch } : item));
  };

  const saveAssetLabel = async (asset) => {
    try {
      const r = await fetch('/api/hospice/video/assets', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, url: asset.url, label: asset.label }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '保存失败');
      updateAssetLocal(asset.url, { label: j.asset?.label || asset.label });
    } catch (err) {
      toast(err.message || '标签保存失败');
    }
  };

  const deleteAsset = async (asset) => {
    try {
      const r = await fetch('/api/hospice/video/assets', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, url: asset.url }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.error || '删除失败');
      setAssets(items => items.filter(item => item.url !== asset.url));
      setStoryboard(items => items.map(scene => (
        scene.media_url === asset.url ? { ...scene, media_url: '', media_type: '' } : scene
      )));
    } catch (err) {
      toast(err.message || '删除失败');
    }
  };

  const generateStoryboard = async () => {
    if (!canStoryboard) {
      toast('患者端还没有可用的生命文档');
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
      if (j.source) {
        setDocument(current => current || j.source.document || '');
        setDocumentStatus(j.source.document_status || documentStatus);
        setDocumentUrl(j.source.document_url || documentUrl);
      }
    } catch (err) {
      toast(err.message || '分镜生成失败');
    } finally {
      setBusy(false);
    }
  };

  const renderVideo = async () => {
    if (!hasStoryboard) {
      toast('请先生成分镜');
      return;
    }
    setBusy(true);
    try {
      const r = await fetch('/api/hospice/video/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: DEVICE_ID, storyboard, narration_voice: narrationVoice }),
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

  const deleteScene = (index) => {
    setStoryboard(items => items.filter((_, i) => i !== index));
  };

  return (
    <div style={screenStyle}>
      <header style={heroStyle}>
        <div>
          <div style={eyebrowStyle}>生命记忆影像</div>
        </div>
      </header>

      <div style={statusRowStyle}>
        <StatusPill active={canStoryboard} label={document ? (documentStatus === 'confirmed' ? '文档已确认' : '文档草稿') : (memoryReady ? '记忆可用' : '等待文档')} />
        <StatusPill active={selectedCount > 0} label={`${selectedCount} 个素材`} />
        <StatusPill active={hasStoryboard} label={`${storyboard.length || 0} 个分镜`} />
      </div>

      <section style={bandStyle}>
        <div style={sectionHeadStyle}>
          <div>
            <div style={sectionTitleStyle}>素材</div>
            <div style={mutedStyle}>图片和视频会按标签匹配到分镜</div>
          </div>
        </div>

        <button onClick={() => fileRef.current?.click()} disabled={busy} style={uploadDropStyle}>
          <span style={uploadIconStyle}>＋</span>
          <span style={uploadTextStyle}>上传照片或视频</span>
        </button>

        <div style={assetScrollerStyle}>
          {assets.length === 0 ? (
            <div style={emptyStyle}>暂无素材</div>
          ) : assets.map(asset => (
            <AssetCard
              key={asset.url}
              asset={asset}
              busy={busy}
              onChange={(patch) => updateAssetLocal(asset.url, patch)}
              onSave={() => saveAssetLabel(asset)}
              onDelete={() => deleteAsset(asset)}
            />
          ))}
        </div>
      </section>

      <section style={bandStyle}>
        <div style={sectionHeadStyle}>
          <div>
            <div style={sectionTitleStyle}>生命文档</div>
            <div style={mutedStyle}>{document ? `${document.length} 字` : '患者端生成后自动读取'}</div>
          </div>
          {documentUrl && <a href={documentUrl} download style={smallLinkStyle}>Word</a>}
        </div>
        <textarea
          value={document}
          onChange={e => setDocument(e.target.value)}
          placeholder="患者端生成后会自动读取；也可以在这里预览和临时修改"
          rows={8}
          style={documentEditorStyle}
        />
      </section>

      <section style={bandStyle}>
        <div style={sectionHeadStyle}>
          <div>
            <div style={sectionTitleStyle}>分镜</div>
            <div style={mutedStyle}>{hasStoryboard ? '可以修改标题、旁白和素材' : '先生成分镜，再生成视频'}</div>
          </div>
          <button onClick={generateStoryboard} disabled={busy || !canStoryboard} style={primaryButtonStyle}>
            {busy ? '处理中' : hasStoryboard ? '重新生成' : '生成分镜'}
          </button>
        </div>

        {hasStoryboard ? (
          <div style={sceneListStyle}>
            {storyboard.map((scene, index) => (
              <SceneEditor
                key={`${scene.title}-${index}`}
                scene={scene}
                index={index}
                assets={assets}
                onChange={(patch) => updateScene(index, patch)}
                onDelete={() => deleteScene(index)}
              />
            ))}
          </div>
        ) : (
          <div style={emptyPanelStyle}>分镜生成后会出现在这里</div>
        )}

        <div style={voiceRowStyle}>
          <span style={voiceLabelStyle}>旁白音色</span>
          <select value={narrationVoice} onChange={e => setNarrationVoice(e.target.value)} style={voiceSelectStyle}>
            <option value="longlaoyi_v3">女声 · 老年</option>
            <option value="longlaobo_v3">男声 · 老年</option>
          </select>
        </div>

        <button onClick={renderVideo} disabled={busy || !hasStoryboard} style={renderButtonStyle(hasStoryboard)}>
          {busy && hasStoryboard ? '生成中' : '生成视频'}
        </button>
      </section>

      {task?.status === 'ready' && (
        <section style={bandStyle}>
          <div style={sectionTitleStyle}>生成结果</div>
          <video src={task.output_url} controls style={videoStyle} />
        </section>
      )}

      {flash && <div style={toastStyle}>{flash}</div>}
      <input ref={fileRef} type="file" accept="image/*,video/*" multiple onChange={onPickFiles} style={{ display: 'none' }} />
    </div>
  );
}

function StatusPill({ active, label }) {
  return <div style={statusPillStyle(active)}>{label}</div>;
}

function AssetCard({ asset, busy, onChange, onSave, onDelete }) {
  return (
    <div style={assetCardStyle(asset.selected)}>
      <div style={assetPreviewWrapStyle}>
        {asset.type === 'video' ? (
          <video src={asset.url} controls preload="metadata" style={previewMediaStyle} />
        ) : (
          <img src={asset.url} alt={asset.label || asset.file_name} style={previewMediaStyle} />
        )}
        <button
          onClick={() => onChange({ selected: !asset.selected })}
          disabled={busy}
          style={assetSelectStyle(asset.selected)}
        >
          {asset.selected ? '已选' : '未选'}
        </button>
      </div>
      <div style={assetBodyStyle}>
        <input
          value={asset.label || ''}
          onChange={e => onChange({ label: e.target.value })}
          onBlur={onSave}
          style={compactInputStyle}
          placeholder="素材标签"
        />
        <div style={assetMetaStyle}>{asset.file_name}</div>
        <button onClick={onDelete} disabled={busy} style={textDangerStyle}>删除</button>
      </div>
    </div>
  );
}

function SceneEditor({ scene, index, assets, onChange, onDelete }) {
  return (
    <div style={sceneStyle}>
      <div style={sceneTopStyle}>
        <span style={sceneIndexStyle}>{String(index + 1).padStart(2, '0')}</span>
        <input value={scene.title || ''} onChange={e => onChange({ title: e.target.value })} style={sceneTitleInputStyle} />
        <button type="button" onClick={onDelete} style={sceneDeleteStyle}>删除</button>
      </div>
      <textarea value={scene.text || ''} onChange={e => onChange({ text: e.target.value })} rows={3} style={sceneTextStyle} />
      <select value={scene.media_url || ''} onChange={e => {
        const asset = assets.find(item => item.url === e.target.value);
        onChange({ media_url: e.target.value, media_type: asset?.type || '' });
      }} style={selectStyle}>
        <option value="">无素材画面</option>
        {assets.filter(item => item.selected).map(asset => <option key={asset.url} value={asset.url}>{asset.label}</option>)}
      </select>
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

function hasMemory(memory) {
  return Object.values(memory || {}).some(items => Array.isArray(items) && items.length);
}

function trimDocument(value) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

const screenStyle = {
  position: 'absolute',
  inset: '0 0 80px 0',
  overflow: 'auto',
  padding: '34px 14px 18px',
  animation: 'fadeUp .4s ease',
};
const heroStyle = { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 14 };
const eyebrowStyle = { fontSize: 24, color: C.amber, fontFamily: 'Noto Sans SC', fontWeight: 600, marginBottom: 4 };
const titleStyle = { margin: 0, maxWidth: 260, fontSize: 22, lineHeight: 1.25, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 500, letterSpacing: 0 };
const statusRowStyle = { display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 10, marginBottom: 4 };
const statusPillStyle = (active) => ({ flex: '0 0 auto', height: 28, display: 'inline-flex', alignItems: 'center', padding: '0 10px', borderRadius: 999, border: `1px solid ${active ? C.sage : C.mist}55`, background: active ? 'rgba(122,148,128,.16)' : 'rgba(255,250,242,.62)', color: active ? C.ink : C.inkFaint, fontSize: 12, fontFamily: 'Noto Sans SC' });
const bandStyle = { borderTop: `1px solid ${C.mist}26`, padding: '14px 0 16px' };
const sectionHeadStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 };
const sectionTitleStyle = { fontSize: 16, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 500 };
const mutedStyle = { fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', marginTop: 3, lineHeight: 1.35 };
const uploadDropStyle = { width: '100%', minHeight: 88, border: `1px dashed ${C.amber}88`, borderRadius: 8, background: 'rgba(255,250,242,.58)', color: C.ink, display: 'grid', placeItems: 'center', gap: 3, padding: 14, cursor: 'pointer', marginBottom: 12 };
const uploadIconStyle = { width: 34, height: 34, borderRadius: 999, display: 'grid', placeItems: 'center', background: `${C.amber}2f`, color: C.ink, fontSize: 24, lineHeight: 1 };
const uploadTextStyle = { fontFamily: 'Noto Sans SC', fontSize: 15, fontWeight: 600 };
const assetScrollerStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))', gap: 10 };
const assetCardStyle = (selected) => ({ minWidth: 0, overflow: 'hidden', border: `1px solid ${selected ? C.amber : C.mist}55`, borderRadius: 8, background: selected ? `${C.amber}14` : 'rgba(255,250,242,.64)' });
const assetPreviewWrapStyle = { position: 'relative', aspectRatio: '1 / 1', background: 'rgba(30,24,16,.12)' };
const previewMediaStyle = { display: 'block', width: '100%', height: '100%', objectFit: 'cover' };
const assetSelectStyle = (selected) => ({ position: 'absolute', top: 8, right: 8, border: 0, borderRadius: 999, height: 26, padding: '0 9px', color: selected ? '#fff' : C.ink, background: selected ? C.sage : 'rgba(255,250,242,.88)', fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' });
const assetBodyStyle = { padding: 8 };
const compactInputStyle = { width: '100%', boxSizing: 'border-box', height: 34, border: `1px solid ${C.mist}33`, borderRadius: 6, padding: '0 8px', background: 'rgba(255,250,242,.86)', color: C.ink, fontFamily: 'Noto Sans SC', outline: 'none' };
const assetMetaStyle = { marginTop: 6, fontSize: 11, color: C.inkFaint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
const textDangerStyle = { marginTop: 8, border: 0, background: 'transparent', color: '#813d32', padding: 0, fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' };
const documentEditorStyle = { width: '100%', boxSizing: 'border-box', minHeight: 168, borderRadius: 8, border: `1px solid ${C.mist}26`, background: 'rgba(255,250,242,.58)', padding: 11, color: C.inkMid, fontSize: 13, lineHeight: 1.65, fontFamily: 'Noto Sans SC', resize: 'vertical', outline: 'none' };
const primaryButtonStyle = { height: 36, border: `1px solid ${C.amber}70`, background: `${C.amber}24`, color: C.ink, borderRadius: 8, padding: '0 13px', fontFamily: 'Noto Sans SC', cursor: 'pointer', whiteSpace: 'nowrap' };
const sceneListStyle = { display: 'grid', gap: 10 };
const emptyPanelStyle = { minHeight: 76, borderRadius: 8, border: `1px solid ${C.mist}24`, background: 'rgba(255,250,242,.45)', display: 'grid', placeItems: 'center', color: C.inkFaint, fontSize: 13, fontFamily: 'Noto Sans SC' };
const sceneStyle = { display: 'grid', gap: 8, borderRadius: 8, border: `1px solid ${C.mist}28`, background: 'rgba(255,250,242,.62)', padding: 10 };
const sceneTopStyle = { display: 'grid', gridTemplateColumns: '34px minmax(0, 1fr) 46px', gap: 8, alignItems: 'center' };
const sceneIndexStyle = { height: 30, borderRadius: 999, display: 'grid', placeItems: 'center', background: `${C.sage}22`, color: C.inkMid, fontSize: 12, fontFamily: 'Noto Sans SC' };
const sceneTitleInputStyle = { ...compactInputStyle, fontWeight: 600 };
const sceneDeleteStyle = { height: 30, border: 0, borderRadius: 6, background: 'rgba(148,65,47,.10)', color: '#813d32', fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' };
const sceneTextStyle = { ...compactInputStyle, minHeight: 86, height: 'auto', resize: 'vertical', lineHeight: 1.5, padding: 9 };
const selectStyle = { ...compactInputStyle, color: C.inkMid };
const voiceRowStyle = { display: 'grid', gridTemplateColumns: '72px 1fr', alignItems: 'center', gap: 10, marginTop: 12 };
const voiceLabelStyle = { color: C.inkFaint, fontSize: 13, fontFamily: 'Noto Sans SC' };
const voiceSelectStyle = { ...compactInputStyle, color: C.inkMid };
const renderButtonStyle = (enabled) => ({ width: '100%', height: 44, marginTop: 12, border: `1px solid ${enabled ? C.green : C.mist}66`, background: enabled ? 'rgba(90,144,112,.20)' : 'rgba(255,250,242,.58)', color: enabled ? C.ink : C.inkFaint, borderRadius: 8, fontFamily: 'Noto Sans SC', fontSize: 15, fontWeight: 600, cursor: enabled ? 'pointer' : 'default' });
const videoStyle = { display: 'block', width: '100%', borderRadius: 8, background: '#111', marginTop: 10 };
const smallLinkStyle = { display: 'inline-flex', alignItems: 'center', height: 34, padding: '0 12px', borderRadius: 8, border: `1px solid ${C.amber}66`, color: C.ink, background: `${C.amber}20`, textDecoration: 'none', fontSize: 13, fontFamily: 'Noto Sans SC', whiteSpace: 'nowrap' };
const emptyStyle = { minHeight: 80, borderRadius: 8, border: `1px solid ${C.mist}22`, display: 'grid', placeItems: 'center', color: C.inkFaint, fontSize: 13, fontFamily: 'Noto Sans SC', background: 'rgba(255,250,242,.44)' };
const toastStyle = { position: 'fixed', bottom: 92, left: '50%', transform: 'translateX(-50%)', maxWidth: 'calc(100vw - 40px)', background: C.ink, color: '#fff', borderRadius: 14, padding: '8px 14px', fontSize: 13, zIndex: 100, fontFamily: 'Noto Sans SC' };
