import { useState } from 'react';
import { C } from '../theme';

function formatSegmentTime(value) {
  const total = Number(value);
  if (!Number.isFinite(total) || total < 0) return '';
  const minutes = Math.floor(total / 60);
  const seconds = Math.floor(total % 60);
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export default function InterviewAudioEditor({ segments, busy, onToggleSegment, onSave }) {
  const [open, setOpen] = useState(false);
  const list = Array.isArray(segments) ? segments : [];
  const deletedCount = list.filter(item => item.deleted).length;
  if (!list.length) {
    return (
      <section style={interviewPanelStyle}>
        <div style={sectionHeadStyle}>
          <div>
            <div style={sectionTitleStyle}>访谈语音编辑</div>
            <div style={subTextStyle}>开始访谈后，这里会显示患者发言片段；有录音时可播放原声，再决定删除或保留。</div>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section style={interviewPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>访谈语音编辑</div>
          <div style={subTextStyle}>
            共 {list.length} 段，已标记删除 {deletedCount} 段。有录音时可播放原声；保存后，人生故事、家信和传承卡片会避开这些片段。
          </div>
        </div>
        <div style={headActionsStyle}>
          <button type="button" onClick={() => setOpen(value => !value)} style={smallButtonStyle(true)}>
            {open ? '收起片段' : '编辑片段'}
          </button>
          <button type="button" onClick={() => onSave(list)} disabled={busy} style={smallButtonStyle(true)}>
            {busy ? '保存中' : '保存编辑'}
          </button>
        </div>
      </div>
      {open && (
        <div style={segmentListStyle}>
          {list.map((segment, index) => {
            const start = formatSegmentTime(segment.start_time);
            const end = formatSegmentTime(segment.end_time);
            const timeText = start && end ? `${start} - ${end}` : `第 ${index + 1} 段`;
            return (
              <div key={segment.id || index} style={segmentItemStyle(segment.deleted)}>
                <div style={segmentMetaStyle}>
                  <span>{timeText}</span>
                  <button type="button" onClick={() => onToggleSegment(segment.id)} style={segmentDeleteButtonStyle(segment.deleted)}>
                    {segment.deleted ? '恢复' : '删除'}
                  </button>
                </div>
                {segment.audio_url && (
                  <audio src={segment.audio_url} controls preload="metadata" style={segmentAudioStyle} />
                )}
                <div style={segmentTextStyle(segment.deleted)}>{segment.text}</div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

const interviewPanelStyle = { padding: '4px 0 18px', borderBottom: `1px solid ${C.mist}22` };
const sectionHeadStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 };
const sectionTitleStyle = { color: C.ink, fontSize: 20, fontFamily: 'Noto Serif SC, serif', fontWeight: 600 };
const subTextStyle = { color: C.inkFaint, fontSize: 15, lineHeight: 1.6 };
const headActionsStyle = { display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' };
const smallButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.sage : C.mist}66`, background: enabled ? `${C.sage}22` : 'rgba(255,250,242,.52)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap', fontFamily: 'Noto Sans SC' });
const segmentListStyle = { display: 'grid', gap: 10, marginTop: 12 };
const segmentItemStyle = (deleted) => ({ display: 'grid', gap: 8, padding: '12px 14px', borderRadius: 8, border: `1px solid ${deleted ? C.red : C.mist}33`, background: deleted ? 'rgba(176,78,60,.08)' : 'rgba(255,250,242,.56)' });
const segmentMetaStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, color: C.inkFaint, fontSize: 13, fontWeight: 700 };
const segmentDeleteButtonStyle = (deleted) => ({ height: 32, padding: '0 12px', borderRadius: 8, border: `1px solid ${deleted ? C.sage : C.red}66`, background: deleted ? `${C.sage}18` : 'rgba(176,78,60,.1)', color: deleted ? C.ink : C.red, fontSize: 14, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: 'pointer', whiteSpace: 'nowrap' });
const segmentAudioStyle = { width: '100%', height: 34 };
const segmentTextStyle = (deleted) => ({ color: deleted ? C.inkFaint : C.inkMid, fontSize: 15, lineHeight: 1.75, textDecoration: deleted ? 'line-through' : 'none' });
