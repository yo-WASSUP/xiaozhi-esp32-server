import { useEffect, useRef, useState } from 'react';
import { C } from '../theme';

function hasMemory(memory) {
  return Object.values(memory || {}).some(items => Array.isArray(items) && items.length);
}

function memoryText(memory) {
  if (!hasMemory(memory)) return '暂无结构化记忆';
  return JSON.stringify(memory, null, 2);
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
  paused,
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

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  const submit = () => {
    const value = text.trim();
    if (!value || busy) return;
    onRunTurn(value);
    setText('');
  };

  return (
    <div style={screenStyle}>
      <header style={headerStyle}>
        <div>
          <div style={titleStyle}>尊严访谈调试</div>
          <div style={subStyle}>文本回合、结构化状态、记忆和人生故事调试保留在这里。</div>
        </div>
        <div style={buttonRowStyle}>
          <button onClick={onToggleVoiceMode} disabled={busy} style={buttonStyle(voiceMode && !paused)}>
            {paused ? '继续访谈' : voiceMode ? (recording ? '暂停访谈' : '语音') : '语音'}
          </button>
          <button onClick={onGenerateDocument} disabled={busy || documentBusy} style={buttonStyle(true)}>
            {documentBusy ? '生成中' : '生成故事'}
          </button>
          <button onClick={onReset} disabled={busy} style={buttonStyle(false)}>重置</button>
        </div>
      </header>

      <main style={contentStyle}>
        <section ref={scrollRef} style={turnsStyle}>
          {openingReply && (
            <div style={assistantStyle}>
              <div style={metaStyle}>AI 开场</div>
              {openingReply}
            </div>
          )}
          {turns.map((turn, index) => (
            <div key={`${turn.patient_text}-${index}`} style={turnStyle}>
              <div style={patientStyle}>
                <div style={metaStyle}>患者 · 第 {index + 1} 轮</div>
                {turn.patient_text}
              </div>
              <div style={assistantStyle}>
                <div style={metaStyle}>AI 回复</div>
                {turn.reply}
                <pre style={jsonStyle}>{JSON.stringify(turn, null, 2)}</pre>
              </div>
            </div>
          ))}
          {busy && <div style={subStyle}>AI 正在生成回复...</div>}
        </section>

        <aside style={sideStyle}>
          <section style={panelStyle}>
            <div style={panelTitleStyle}>访谈记忆</div>
            <pre style={sidePreStyle}>{memoryText(status?.dignity_memory)}</pre>
          </section>
          {(document || documentBusy) && (
            <section style={panelStyle}>
              <div style={panelHeadStyle}>
                <div style={panelTitleStyle}>人生故事</div>
                {document && !documentUrl && (
                  <button onClick={() => onConfirmDocument(document)} disabled={documentConfirmBusy} style={smallButtonStyle}>
                    {documentConfirmBusy ? '保存中' : '确认'}
                  </button>
                )}
                {documentUrl && <a href={documentUrl} download style={linkStyle}>Word</a>}
              </div>
              {documentBusy ? (
                <div style={subStyle}>正在生成人生故事...</div>
              ) : (
                <textarea value={document} onChange={e => onDocumentChange(e.target.value)} readOnly={!!documentUrl} style={documentStyle} />
              )}
            </section>
          )}
        </aside>
      </main>

      <footer style={inputBarStyle}>
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
        <button onClick={submit} disabled={busy || !text.trim()} style={sendButtonStyle}>
          {busy ? '处理中' : '发送'}
        </button>
      </footer>
    </div>
  );
}

const screenStyle = { height: '100%', display: 'grid', gridTemplateRows: 'auto 1fr auto', color: C.ink, fontFamily: 'Noto Sans SC', overflow: 'hidden' };
const headerStyle = { padding: '18px 24px 12px', borderBottom: `1px solid ${C.mist}22`, background: 'rgba(255,250,242,.58)', display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'center' };
const titleStyle = { fontSize: 18, fontFamily: 'Noto Serif SC, serif', fontWeight: 500 };
const subStyle = { color: C.inkFaint, fontSize: 12, lineHeight: 1.5 };
const buttonRowStyle = { display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' };
const buttonStyle = (primary) => ({ height: 34, padding: '0 14px', borderRadius: 6, border: `1px solid ${primary ? C.amber : C.mist}66`, background: primary ? `${C.amber}24` : 'rgba(255,250,242,.72)', color: primary ? C.ink : C.inkMid, cursor: 'pointer', fontSize: 13, fontFamily: 'Noto Sans SC', whiteSpace: 'nowrap' });
const contentStyle = { overflow: 'hidden', padding: '18px 24px', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16, minHeight: 0 };
const turnsStyle = { display: 'flex', flexDirection: 'column', gap: 14, minWidth: 0, minHeight: 0, overflow: 'auto' };
const turnStyle = { display: 'flex', flexDirection: 'column', gap: 10 };
const patientStyle = { alignSelf: 'flex-end', maxWidth: '72%', borderRadius: 8, border: `1px solid ${C.amber}44`, background: `${C.amber}22`, padding: '10px 12px', lineHeight: 1.65, fontSize: 14 };
const assistantStyle = { alignSelf: 'flex-start', maxWidth: '86%', borderRadius: 8, border: `1px solid ${C.mist}33`, background: 'rgba(255,250,242,.76)', padding: '11px 13px', lineHeight: 1.7, fontSize: 14 };
const metaStyle = { fontSize: 11, color: C.inkFaint, marginBottom: 4 };
const jsonStyle = { margin: '8px 0 0', padding: 10, maxHeight: 220, overflow: 'auto', border: `1px solid ${C.mist}22`, borderRadius: 6, background: 'rgba(255,250,242,.68)', color: C.inkMid, fontSize: 11, lineHeight: 1.45, whiteSpace: 'pre-wrap', wordBreak: 'break-word' };
const sideStyle = { display: 'grid', gap: 12, alignSelf: 'stretch', minWidth: 0, minHeight: 0, overflow: 'auto', alignContent: 'start' };
const panelStyle = { border: `1px solid ${C.mist}33`, borderRadius: 8, background: 'rgba(255,250,242,.78)', padding: 12, minWidth: 0 };
const panelHeadStyle = { display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8 };
const panelTitleStyle = { fontSize: 14, color: C.ink, marginBottom: 8, fontFamily: 'Noto Serif SC, serif' };
const sidePreStyle = { margin: 0, color: C.inkMid, fontSize: 12, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' };
const documentStyle = { width: '100%', minHeight: 180, resize: 'vertical', boxSizing: 'border-box', border: `1px solid ${C.mist}22`, borderRadius: 6, padding: '9px 10px', outline: 'none', color: C.inkMid, fontSize: 12, lineHeight: 1.6, fontFamily: 'Noto Sans SC' };
const smallButtonStyle = { height: 30, padding: '0 10px', borderRadius: 6, border: `1px solid ${C.amber}66`, background: `${C.amber}20`, color: C.ink, fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap', fontFamily: 'Noto Sans SC' };
const linkStyle = { display: 'inline-flex', alignItems: 'center', height: 30, padding: '0 10px', borderRadius: 6, border: `1px solid ${C.amber}66`, color: C.ink, background: `${C.amber}20`, fontSize: 12, textDecoration: 'none', whiteSpace: 'nowrap' };
const inputBarStyle = { borderTop: `1px solid ${C.mist}22`, padding: '12px 18px 16px', background: 'rgba(243,233,212,.46)', display: 'grid', gridTemplateColumns: '1fr auto', gap: 10 };
const textareaStyle = { width: '100%', resize: 'none', border: `1px solid ${C.mist}44`, borderRadius: 6, background: 'rgba(255,250,242,.82)', color: C.ink, padding: '10px 11px', fontSize: 14, lineHeight: 1.55, outline: 'none', boxSizing: 'border-box', fontFamily: 'Noto Sans SC' };
const sendButtonStyle = { minWidth: 72, borderRadius: 6, border: `1px solid ${C.amber}66`, background: `${C.amber}24`, color: C.ink, cursor: 'pointer', fontSize: 13, fontFamily: 'Noto Sans SC' };
