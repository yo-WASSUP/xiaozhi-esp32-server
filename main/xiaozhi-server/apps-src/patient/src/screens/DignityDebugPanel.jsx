import { useMemo, useRef, useState, useEffect } from 'react';
import { C } from '../theme';

const STAGE_LABELS = {
  rapport: '建立关系',
  life_review: '人生回顾',
  values: '价值提炼',
  relationships: '重要关系',
  legacy_message: '留言祝福',
  summary_confirm: '总结确认',
};

const STRATEGY_LABELS = {
  continue_deeper: '继续访谈',
  comfort: '安抚承接',
  pause: '暂停',
  switch_topic: '转换话题',
  ask_photo_context: '照片线索',
  output_rewrite: '安全边界',
  handoff_nurse: '人工介入',
  simple_followup: '轻量追问',
  summarize_confirm: '总结确认',
};

const MOOD_LABELS = {
  calm: '平静',
  happy: '开心',
  sad: '难过',
  anxious: '焦虑',
  angry: '生气',
  tired: '疲惫',
  nostalgic: '怀旧',
  grateful: '感激',
  lonely: '孤独',
};

const ENGAGEMENT_LABELS = {
  high: '高',
  medium: '中',
  low: '低',
};

const MEMORY_LABELS = {
  life_story_materials: '生命故事',
  important_relationships: '重要关系',
  values_and_strengths: '价值与力量',
  messages_to_family: '留给家人的话',
};

const EXAMPLES = [
  '我年轻时在厂里拿过先进，那时候大家都挺认可我。',
  '我有点累了，不太想说了。',
  '我和老伴那张结婚照还在柜子里。',
  '我想我的女儿了。',
];

function labelOf(map, value) {
  return map[value] || value || '-';
}

function formatLatency(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 1000) return `${Math.round(value)}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function responseLatencyOf(value) {
  return value?.client_response_latency_ms ?? value?.response_latency_ms;
}

function formatMemoryItem(item) {
  if (typeof item === 'string') return item;
  if (!item || typeof item !== 'object') return String(item ?? '');
  return Object.entries(item)
    .filter(([, value]) => value !== undefined && value !== null && `${value}`.trim())
    .map(([key, value]) => `${key}: ${value}`)
    .join('；');
}

function hasMemory(memory) {
  return Object.values(memory || {}).some(items => Array.isArray(items) && items.length);
}

function DecisionLine({ turn }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10, fontSize: 12, color: C.inkFaint }}>
      <span>阶段 {labelOf(STAGE_LABELS, turn.current_stage)}</span>
      <span>策略 {labelOf(STRATEGY_LABELS, turn.strategy)}</span>
      <span>情绪 {labelOf(MOOD_LABELS, turn.emotion_state?.mood)}</span>
      <span>投入 {labelOf(ENGAGEMENT_LABELS, turn.emotion_state?.engagement)}</span>
      {formatLatency(responseLatencyOf(turn)) && <span>回复耗时 {formatLatency(responseLatencyOf(turn))}</span>}
    </div>
  );
}

function MemoryPanel({ memory }) {
  if (!hasMemory(memory)) {
    return (
      <div style={memoryPanelStyle}>
        <div style={memoryTitleStyle}>访谈记忆</div>
        <div style={{ color: C.inkFaint, fontSize: 12 }}>还没有沉淀出可显示的记忆。</div>
      </div>
    );
  }

  return (
    <div style={memoryPanelStyle}>
      <div style={memoryTitleStyle}>访谈记忆</div>
      <div style={{ display: 'grid', gap: 8 }}>
        {Object.entries(MEMORY_LABELS).map(([key, label]) => {
          const items = memory?.[key];
          if (!Array.isArray(items) || !items.length) return null;
          return (
            <div key={key}>
              <div style={{ fontSize: 12, color: C.ink, marginBottom: 3 }}>{label}</div>
              <div style={{ display: 'grid', gap: 3 }}>
                {items.map((item, index) => (
                  <div key={`${key}-${index}`} style={{ fontSize: 12, color: C.inkMid, lineHeight: 1.45 }}>
                    {formatMemoryItem(item)}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DocumentPanel({ document, documentUrl, busy, confirmBusy, onChange, onConfirm }) {
  if (!busy && !document) return null;
  const canConfirm = !!String(document || '').trim() && !busy && !confirmBusy;
  return (
    <div style={documentPanelStyle}>
      <div style={documentHeaderStyle}>
        <div style={{ minWidth: 0 }}>
          <div style={{ ...memoryTitleStyle, marginBottom: 2 }}>生命访谈文档</div>
          {document && !documentUrl && !busy && (
            <div style={{ color: C.inkFaint, fontSize: 11 }}>请核对事实并修改，确认后再生成 Word</div>
          )}
          {documentUrl && (
            <div style={{ color: C.inkFaint, fontSize: 11 }}>已确认，可下载 Word</div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {document && !documentUrl && !busy && (
            <button onClick={() => onConfirm(document)} disabled={!canConfirm} style={confirmButtonStyle(canConfirm)}>
              {confirmBusy ? '保存中' : '确认'}
            </button>
          )}
          {documentUrl && (
            <a href={documentUrl} download style={downloadLinkStyle}>
              Word
            </a>
          )}
        </div>
      </div>
      {busy ? (
        <div style={{ color: C.inkFaint, fontSize: 12 }}>正在生成文档...</div>
      ) : (
        <textarea
          value={document}
          onChange={e => onChange(e.target.value)}
          readOnly={!!documentUrl}
          style={{
            ...documentEditorStyle,
            background: documentUrl ? 'rgba(255,250,242,.54)' : 'rgba(255,250,242,.82)',
          }}
        />
      )}
    </div>
  );
}

function JsonDetails({ turn }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginTop: 8 }}>
      <button onClick={() => setOpen(v => !v)} style={linkButtonStyle}>
        {open ? '收起结构化结果' : '查看结构化结果'}
      </button>
      {open && (
        <pre style={jsonStyle}>
          {JSON.stringify(turn, null, 2)}
        </pre>
      )}
    </div>
  );
}

function PatientBubble({ text, index }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <div style={patientBubbleStyle}>
        <div style={{ fontSize: 11, color: C.inkFaint, marginBottom: 4 }}>患者 · 第 {index + 1} 轮</div>
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({ turn, opening }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
      <div style={assistantBubbleStyle}>
        <div style={{ fontSize: 11, color: C.inkFaint, marginBottom: 4 }}>{opening ? 'AI 主动开场' : 'AI 访谈回复'}</div>
        {turn.reply}
        {!opening && <DecisionLine turn={turn} />}
        {!opening && <JsonDetails turn={turn} />}
      </div>
    </div>
  );
}

export default function DignityDebugPanel({
  turns,
  status,
  openingReply,
  busy,
  documentBusy,
  documentConfirmBusy,
  document,
  documentUrl,
  voiceMode,
  recording,
  onRunTurn,
  onReset,
  onGenerateDocument,
  onConfirmDocument,
  onDocumentChange,
  onToggleVoiceMode,
}) {
  const [text, setText] = useState('');
  const scrollRef = useRef(null);

  const openingMessage = useMemo(() => {
    if (!openingReply) return null;
    return { reply: openingReply };
  }, [openingReply]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, openingMessage, busy]);

  const submit = () => {
    const value = text.trim();
    if (!value || busy) return;
    onRunTurn(value);
    setText('');
  };

  return (
    <div style={{ height: '100%', display: 'grid', gridTemplateRows: 'auto 1fr auto', color: C.ink, fontFamily: 'Noto Sans SC', overflow: 'hidden' }}>
      <div style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 18, fontFamily: 'Noto Serif SC, serif', fontWeight: 400, letterSpacing: '.08em' }}>尊严访谈调试对话</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9, fontSize: 12, color: C.inkFaint, marginTop: 5 }}>
              <span>文本模式</span>
              <span>不播放 TTS</span>
              <span>{labelOf(STAGE_LABELS, status?.current_stage || 'rapport')}</span>
              <span>{labelOf(STRATEGY_LABELS, status?.strategy || 'continue_deeper')}</span>
              <span>情绪 {labelOf(MOOD_LABELS, status?.emotion_state?.mood)}</span>
              <span>投入 {labelOf(ENGAGEMENT_LABELS, status?.emotion_state?.engagement)}</span>
              {formatLatency(responseLatencyOf(status)) && <span>回复耗时 {formatLatency(responseLatencyOf(status))}</span>}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={onToggleVoiceMode} disabled={busy} style={buttonStyle(voiceMode)}>
              {voiceMode ? (recording ? '语音访谈中' : '语音访谈') : '语音访谈'}
            </button>
            <button onClick={onGenerateDocument} disabled={busy || documentBusy} style={buttonStyle(true)}>
              {documentBusy ? '生成中' : '生成文档'}
            </button>
            <button onClick={onReset} disabled={busy} style={buttonStyle(false)}>重置</button>
          </div>
        </div>
      </div>

      <div style={{ overflow: 'hidden', padding: '18px 24px', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 300px', gap: 16, minHeight: 0 }}>
        <div ref={scrollRef} style={{ display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0, minHeight: 0, overflow: 'auto' }}>
          {openingMessage && <AssistantBubble turn={openingMessage} opening />}
          {turns.map((turn, index) => (
            <div key={`${turn.patient_text}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <PatientBubble text={turn.patient_text} index={index} />
              <AssistantBubble turn={turn} />
            </div>
          ))}
          {busy && (
            <div style={{ color: C.inkFaint, fontSize: 13, padding: '6px 2px' }}>AI 正在生成回复...</div>
          )}
        </div>
        <div style={{
          display: 'grid',
          gap: 12,
          alignSelf: 'stretch',
          minWidth: 0,
          minHeight: 0,
          overflow: 'hidden',
          gridTemplateRows: document || documentBusy ? 'minmax(160px, 42%) minmax(0, 1fr)' : 'minmax(0, 1fr)',
        }}>
          <DocumentPanel
            document={document}
            documentUrl={documentUrl}
            busy={documentBusy}
            confirmBusy={documentConfirmBusy}
            onChange={onDocumentChange}
            onConfirm={onConfirmDocument}
          />
          <MemoryPanel memory={status?.dignity_memory} />
        </div>
      </div>

      <div style={inputBarStyle}>
        <div style={{ display: 'flex', gap: 8, overflowX: 'auto', marginBottom: 9 }}>
          {EXAMPLES.map(item => (
            <button key={item} onClick={() => setText(item)} style={smallButtonStyle}>{item.slice(0, 10)}</button>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10 }}>
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            placeholder="输入患者回答"
            style={textareaStyle}
          />
          <button onClick={submit} disabled={busy || !text.trim()} style={{ ...buttonStyle(true), height: '100%', minWidth: 72 }}>
            {busy ? '处理中' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}

const headerStyle = {
  padding: '18px 24px 12px',
  borderBottom: `1px solid ${C.mist}22`,
  background: 'rgba(255,250,242,.58)',
};

const inputBarStyle = {
  borderTop: `1px solid ${C.mist}22`,
  padding: '12px 18px 16px',
  background: 'rgba(243,233,212,.46)',
};

const patientBubbleStyle = {
  maxWidth: '72%',
  borderRadius: 8,
  border: `1px solid ${C.amber}44`,
  background: `${C.amber}22`,
  padding: '10px 12px',
  color: C.ink,
  lineHeight: 1.65,
  fontSize: 14,
};

const assistantBubbleStyle = {
  maxWidth: '82%',
  borderRadius: 8,
  border: `1px solid ${C.mist}33`,
  background: 'rgba(255,250,242,.76)',
  padding: '11px 13px',
  color: C.ink,
  lineHeight: 1.7,
  fontSize: 14,
};

const memoryPanelStyle = {
  border: `1px solid ${C.mist}33`,
  borderRadius: 8,
  background: 'rgba(255,250,242,.78)',
  padding: 12,
  minHeight: 0,
  overflow: 'auto',
};

const documentPanelStyle = {
  border: `1px solid ${C.mist}33`,
  borderRadius: 8,
  background: 'rgba(255,250,242,.78)',
  padding: 12,
  minHeight: 0,
  overflow: 'auto',
};

const documentEditorStyle = {
  width: '100%',
  minHeight: 140,
  height: 'calc(100% - 44px)',
  resize: 'none',
  boxSizing: 'border-box',
  border: `1px solid ${C.mist}22`,
  borderRadius: 6,
  padding: '9px 10px',
  outline: 'none',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  color: C.inkMid,
  fontSize: 12,
  lineHeight: 1.6,
  fontFamily: 'Noto Sans SC',
};

const documentHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  marginBottom: 8,
};

const downloadLinkStyle = {
  border: `1px solid ${C.amber}66`,
  borderRadius: 6,
  padding: '4px 9px',
  color: C.ink,
  background: `${C.amber}20`,
  fontSize: 12,
  textDecoration: 'none',
  whiteSpace: 'nowrap',
};

const confirmButtonStyle = (enabled) => ({
  border: `1px solid ${enabled ? C.amber : C.mist}66`,
  borderRadius: 6,
  padding: '4px 9px',
  color: enabled ? C.ink : C.inkFaint,
  background: enabled ? `${C.amber}20` : 'rgba(255,250,242,.52)',
  fontSize: 12,
  cursor: enabled ? 'pointer' : 'not-allowed',
  whiteSpace: 'nowrap',
  fontFamily: 'Noto Sans SC',
});

const memoryTitleStyle = {
  fontSize: 14,
  color: C.ink,
  marginBottom: 10,
  fontFamily: 'Noto Serif SC, serif',
};

const jsonStyle = {
  margin: '8px 0 0',
  padding: 12,
  maxHeight: 240,
  overflow: 'auto',
  border: `1px solid ${C.mist}33`,
  borderRadius: 6,
  background: 'rgba(255,250,242,.72)',
  color: C.inkMid,
  fontSize: 12,
  lineHeight: 1.55,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
};

const textareaStyle = {
  width: '100%',
  resize: 'none',
  border: `1px solid ${C.mist}44`,
  borderRadius: 6,
  background: 'rgba(255,250,242,.82)',
  color: C.ink,
  padding: '10px 11px',
  fontSize: 14,
  lineHeight: 1.55,
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'Noto Sans SC',
};

const buttonStyle = (primary) => ({
  height: 34,
  padding: '0 14px',
  borderRadius: 6,
  border: `1px solid ${primary ? C.amber : C.mist}66`,
  background: primary ? `${C.amber}24` : 'rgba(255,250,242,.72)',
  color: primary ? C.ink : C.inkMid,
  cursor: 'pointer',
  fontSize: 13,
  fontFamily: 'Noto Sans SC',
  whiteSpace: 'nowrap',
});

const smallButtonStyle = {
  height: 28,
  padding: '0 10px',
  borderRadius: 6,
  border: `1px solid ${C.mist}33`,
  background: 'rgba(255,250,242,.62)',
  color: C.inkMid,
  cursor: 'pointer',
  fontSize: 12,
  fontFamily: 'Noto Sans SC',
  whiteSpace: 'nowrap',
};

const linkButtonStyle = {
  border: 0,
  background: 'transparent',
  color: C.inkFaint,
  cursor: 'pointer',
  fontSize: 12,
  padding: 0,
  fontFamily: 'Noto Sans SC',
};
