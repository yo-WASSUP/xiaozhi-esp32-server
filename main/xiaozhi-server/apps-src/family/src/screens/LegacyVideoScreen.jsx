import { useEffect, useMemo, useRef, useState } from 'react';
import { FilmStrip, MusicNotesSimple, UploadSimple } from '@phosphor-icons/react';
import { DEVICE_ID } from '../constants';
import { C } from '../theme';

export default function LegacyVideoScreen() {
  const [document, setDocument] = useState('');
  const [documentStatus, setDocumentStatus] = useState('');
  const [documentUrl, setDocumentUrl] = useState('');
  const [memoryReady, setMemoryReady] = useState(false);
  const [assets, setAssets] = useState([]);
  const [storyboard, setStoryboard] = useState([]);
  const [narrationMode, setNarrationMode] = useState('longlaoyi_v3');
  const [musicMode, setMusicMode] = useState('default');
  const [task, setTask] = useState(null);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState('');
  const fileRef = useRef(null);

  const selectedCount = useMemo(() => assets.filter(item => item.selected).length, [assets]);
  const visualAssets = useMemo(() => assets.filter(item => item.type !== 'audio'), [assets]);
  const musicAssets = useMemo(() => assets.filter(item => item.type === 'audio'), [assets]);
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
        if (!file.type.startsWith('image/') && !file.type.startsWith('video/') && !file.type.startsWith('audio/')) continue;
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
      if (musicMode === asset.url) setMusicMode('default');
    } catch (err) {
      toast(err.message || '删除失败');
    }
  };

  const generateStoryboard = async () => {
    if (!canStoryboard) {
      toast('患者端还没有可用的人生故事');
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
          assets: visualAssets.filter(item => item.selected),
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
      const hasVoiceover = narrationMode !== 'none';
      const hasMusic = musicMode !== 'none';
      const r = await fetch('/api/hospice/video/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: DEVICE_ID,
          storyboard,
          voiceover: hasVoiceover,
          narration_voice: hasVoiceover ? narrationMode : '',
          background_music: hasMusic,
          music_url: hasMusic && musicMode !== 'default' ? musicMode : '',
        }),
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 46, height: 46, borderRadius: 15, background: C.primaryContainer, color: C.amber, display: 'grid', placeItems: 'center' }}>
            <FilmStrip size={24} weight="duotone" />
          </div>
          <div>
            <div style={eyebrowStyle}>生命记忆影像</div>
            <div style={mutedStyle}>整理素材，生成可珍藏的家庭影像</div>
          </div>
        </div>
      </header>

      <div style={statusRowStyle}>
        <StatusPill active={canStoryboard} label={document ? (documentStatus === 'confirmed' ? '故事已确认' : '故事草稿') : (memoryReady ? '记忆可用' : '等待故事')} />
        <StatusPill active={selectedCount > 0} label={`${selectedCount} 个素材`} />
        <StatusPill active={hasStoryboard} label={`${storyboard.length || 0} 个分镜`} />
      </div>

      <section style={bandStyle}>
        <div style={sectionHeadStyle}>
          <div>
            <div style={sectionTitleStyle}>素材</div>
            <div style={mutedStyle}>图片和视频会按标签匹配到分镜，音频可作为背景音乐</div>
          </div>
        </div>

        <button onClick={() => fileRef.current?.click()} disabled={busy} style={uploadDropStyle}>
          <span style={uploadIconStyle}><UploadSimple size={21} weight="bold" /></span>
          <span style={uploadTextStyle}>上传照片、视频或音乐</span>
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
            <div style={sectionTitleStyle}>人生故事</div>
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
                assets={visualAssets}
                onChange={(patch) => updateScene(index, patch)}
                onDelete={() => deleteScene(index)}
              />
            ))}
          </div>
        ) : (
          <div style={emptyPanelStyle}>分镜生成后会出现在这里</div>
        )}

        <div style={optionPanelStyle}>
          <div style={optionGroupStyle}>
            <div style={optionTitleStyle}>旁白</div>
            <div style={segmentGridStyle}>
              <button type="button" onClick={() => setNarrationMode('none')} style={optionButtonStyle(narrationMode === 'none')}>
                无旁白
              </button>
              <button type="button" onClick={() => setNarrationMode('longlaoyi_v3')} style={optionButtonStyle(narrationMode === 'longlaoyi_v3')}>
                女声
              </button>
              <button type="button" onClick={() => setNarrationMode('longlaobo_v3')} style={optionButtonStyle(narrationMode === 'longlaobo_v3')}>
                男声
              </button>
            </div>
          </div>
          <div style={optionGroupStyle}>
            <div style={optionTitleStyle}>背景音乐</div>
            <div style={musicGridStyle}>
              <button type="button" onClick={() => setMusicMode('none')} style={optionButtonStyle(musicMode === 'none')}>
                无音乐
              </button>
              <button type="button" onClick={() => setMusicMode('default')} style={optionButtonStyle(musicMode === 'default')}>
                默认音乐
              </button>
              {musicAssets.map(asset => (
                <button
                  key={asset.url}
                  type="button"
                  onClick={() => setMusicMode(asset.url)}
                  style={optionButtonStyle(musicMode === asset.url)}
                  title={asset.label || asset.file_name}
                >
                  {asset.label || asset.file_name}
                </button>
              ))}
            </div>
          </div>
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
      <input ref={fileRef} type="file" accept="image/*,video/*,audio/*" multiple onChange={onPickFiles} style={{ display: 'none' }} />
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
        {asset.type === 'audio' ? (
          <div style={audioPreviewStyle}>
            <div style={audioIconStyle}><MusicNotesSimple size={24} weight="duotone" /></div>
            <audio src={asset.url} controls preload="metadata" style={audioControlStyle} />
          </div>
        ) : asset.type === 'video' ? (
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
  inset: '0 0 calc(72px + env(safe-area-inset-bottom)) 0',
  overflow: 'auto',
  padding: 'calc(24px + env(safe-area-inset-top)) 16px 24px',
  animation: 'fadeUp .24s cubic-bezier(.2,0,0,1)',
};
const heroStyle = { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 14 };
const eyebrowStyle = { fontSize: 23, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 650, letterSpacing: '-.02em', marginBottom: 2 };
const titleStyle = { margin: 0, maxWidth: 260, fontSize: 22, lineHeight: 1.25, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 650, letterSpacing: 0 };
const statusRowStyle = { display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 10, marginBottom: 4 };
const statusPillStyle = (active) => ({ flex: '0 0 auto', height: 30, display: 'inline-flex', alignItems: 'center', padding: '0 11px', borderRadius: 12, border: `1px solid ${active ? C.amber : C.outline}`, background: active ? C.primaryContainer : '#fff', color: active ? C.amber : C.inkFaint, fontSize: 12, fontFamily: 'Noto Sans SC', fontWeight: 500 });
const bandStyle = { borderTop: `1px solid ${C.mist}26`, padding: '14px 0 16px' };
const sectionHeadStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 };
const sectionTitleStyle = { fontSize: 17, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 650 };
const mutedStyle = { fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', marginTop: 3, lineHeight: 1.35 };
const uploadDropStyle = { width: '100%', minHeight: 96, border: `1px dashed ${C.amber}88`, borderRadius: 16, background: '#fff', color: C.ink, display: 'grid', placeItems: 'center', gap: 5, padding: 14, cursor: 'pointer', marginBottom: 12 };
const uploadIconStyle = { width: 40, height: 40, borderRadius: 14, display: 'grid', placeItems: 'center', background: C.primaryContainer, color: C.amber, lineHeight: 1 };
const uploadTextStyle = { fontFamily: 'Noto Sans SC', fontSize: 15, fontWeight: 600 };
const assetScrollerStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(148px, 1fr))', gap: 10 };
const assetCardStyle = (selected) => ({ minWidth: 0, overflow: 'hidden', border: `1px solid ${selected ? C.amber : C.outline}`, borderRadius: 16, background: selected ? C.primaryContainer : '#fff' });
const assetPreviewWrapStyle = { position: 'relative', aspectRatio: '1 / 1', background: 'rgba(30,24,16,.12)' };
const previewMediaStyle = { display: 'block', width: '100%', height: '100%', objectFit: 'cover' };
const audioPreviewStyle = { width: '100%', height: '100%', display: 'grid', alignContent: 'center', justifyItems: 'center', gap: 12, padding: 12, boxSizing: 'border-box', background: C.primaryContainer };
const audioIconStyle = { width: 44, height: 44, borderRadius: 14, display: 'grid', placeItems: 'center', background: '#fff', color: C.amber, fontFamily: 'Noto Sans SC' };
const audioControlStyle = { width: '100%', maxWidth: 132 };
const assetSelectStyle = (selected) => ({ position: 'absolute', top: 8, right: 8, border: 0, borderRadius: 10, height: 28, padding: '0 9px', color: selected ? '#fff' : C.ink, background: selected ? C.sage : 'rgba(255,255,255,.92)', fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' });
const assetBodyStyle = { padding: 8 };
const compactInputStyle = { width: '100%', boxSizing: 'border-box', height: 40, border: `1px solid ${C.outline}`, borderRadius: 12, padding: '0 10px', background: '#fff', color: C.ink, fontFamily: 'Noto Sans SC', outline: 'none' };
const assetMetaStyle = { marginTop: 6, fontSize: 11, color: C.inkFaint, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
const textDangerStyle = { marginTop: 8, border: 0, background: 'transparent', color: '#813d32', padding: 0, fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' };
const documentEditorStyle = { width: '100%', boxSizing: 'border-box', minHeight: 168, borderRadius: 16, border: `1px solid ${C.outline}`, background: '#fff', padding: 12, color: C.inkMid, fontSize: 13, lineHeight: 1.65, fontFamily: 'Noto Sans SC', resize: 'vertical', outline: 'none' };
const primaryButtonStyle = { height: 44, border: `1px solid ${C.amber}70`, background: C.primaryContainer, color: C.amber, borderRadius: 14, padding: '0 14px', fontFamily: 'Noto Sans SC', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' };
const sceneListStyle = { display: 'grid', gap: 10 };
const emptyPanelStyle = { minHeight: 76, borderRadius: 16, border: `1px solid ${C.outline}`, background: '#fff', display: 'grid', placeItems: 'center', color: C.inkFaint, fontSize: 13, fontFamily: 'Noto Sans SC' };
const sceneStyle = { display: 'grid', gap: 8, borderRadius: 16, border: `1px solid ${C.outline}`, background: '#fff', padding: 12 };
const sceneTopStyle = { display: 'grid', gridTemplateColumns: '34px minmax(0, 1fr) 46px', gap: 8, alignItems: 'center' };
const sceneIndexStyle = { height: 32, borderRadius: 10, display: 'grid', placeItems: 'center', background: C.primaryContainer, color: C.amber, fontSize: 12, fontFamily: 'Noto Sans SC' };
const sceneTitleInputStyle = { ...compactInputStyle, fontWeight: 600 };
const sceneDeleteStyle = { height: 32, border: 0, borderRadius: 10, background: `${C.red}12`, color: C.red, fontSize: 12, fontFamily: 'Noto Sans SC', cursor: 'pointer' };
const sceneTextStyle = { ...compactInputStyle, minHeight: 86, height: 'auto', resize: 'vertical', lineHeight: 1.5, padding: 9 };
const selectStyle = { ...compactInputStyle, color: C.inkMid };
const optionPanelStyle = { display: 'grid', gap: 14, marginTop: 12, padding: 12, borderRadius: 16, border: `1px solid ${C.outline}`, background: '#fff' };
const optionGroupStyle = { display: 'grid', gap: 8 };
const optionTitleStyle = { color: C.inkMid, fontSize: 13, fontFamily: 'Noto Sans SC', fontWeight: 600 };
const segmentGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 };
const musicGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 };
const optionButtonStyle = (active) => ({
  minWidth: 0,
  height: 40,
  border: `1px solid ${active ? C.amber : C.mist}66`,
  borderRadius: 12,
  padding: '0 8px',
  background: active ? C.primaryContainer : '#fff',
  color: active ? C.amber : C.inkMid,
  fontFamily: 'Noto Sans SC',
  fontSize: 13,
  fontWeight: active ? 600 : 400,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  cursor: 'pointer',
});
const renderButtonStyle = (enabled) => ({ width: '100%', height: 48, marginTop: 12, border: 0, background: enabled ? C.amber : C.surfaceVariant, color: enabled ? C.onPrimary : C.inkFaint, borderRadius: 14, fontFamily: 'Noto Sans SC', fontSize: 15, fontWeight: 650, cursor: enabled ? 'pointer' : 'default' });
const videoStyle = { display: 'block', width: '100%', borderRadius: 16, background: '#111', marginTop: 10 };
const smallLinkStyle = { display: 'inline-flex', alignItems: 'center', height: 40, padding: '0 12px', borderRadius: 12, border: `1px solid ${C.amber}66`, color: C.amber, background: C.primaryContainer, textDecoration: 'none', fontSize: 13, fontWeight: 600, fontFamily: 'Noto Sans SC', whiteSpace: 'nowrap' };
const emptyStyle = { minHeight: 80, borderRadius: 16, border: `1px solid ${C.outline}`, display: 'grid', placeItems: 'center', color: C.inkFaint, fontSize: 13, fontFamily: 'Noto Sans SC', background: '#fff' };
const toastStyle = { position: 'fixed', bottom: 92, left: '50%', transform: 'translateX(-50%)', maxWidth: 'calc(100vw - 40px)', background: C.ink, color: '#fff', borderRadius: 14, padding: '8px 14px', fontSize: 13, zIndex: 100, fontFamily: 'Noto Sans SC' };
