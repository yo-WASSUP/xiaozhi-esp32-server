import { useState } from 'react';
import { C } from '../theme';

const MIN_MEMORY_ITEMS_FOR_DOCUMENT = 6;

const MEMORY_LABELS = {
  life_story_materials: '人生经历',
  important_relationships: '重要关系',
  values_and_strengths: '珍视与力量',
  messages_to_family: '给家人的话',
};

function collectMemorySections(memory) {
  return Object.entries(memory || {})
    .map(([key, value]) => {
      const items = Array.isArray(value) ? value.filter(Boolean) : [];
      return {
        key,
        title: MEMORY_LABELS[key] || key,
        items,
      };
    })
    .filter(section => section.items.length);
}

function MemoryPanel({
  sections,
  itemCount,
  ready,
  busy,
  cardBusy,
  letterBusy,
  onGenerateDocument,
  onGenerateLegacyCard,
  onGenerateFamilyLetter,
}) {
  const [open, setOpen] = useState(false);
  return (
    <section style={memoryPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <span style={sectionTitleStyle}>生命记忆</span>
          <span style={memoryCountStyle}>{itemCount} 条</span>
        </div>
        <div style={headActionsStyle}>
          <button onClick={() => setOpen(v => !v)} style={memoryToggleStyle}>
            {open ? '收起记忆' : '展开记忆'}
          </button>
          <button
            onClick={onGenerateDocument}
            disabled={busy || !ready}
            title={ready ? '' : `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`}
            style={generateButtonStyle(ready)}
          >
            {busy ? '正在整理' : ready ? '生成人生故事' : '记忆不足'}
          </button>
          <button
            onClick={onGenerateLegacyCard}
            disabled={cardBusy || !ready}
            title={ready ? '' : `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`}
            style={cardButtonStyle(ready)}
          >
            {cardBusy ? '生成中' : ready ? '生成传承卡片' : '记忆不足'}
          </button>
          <button
            onClick={onGenerateFamilyLetter}
            disabled={letterBusy || !ready}
            title={ready ? '' : `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`}
            style={letterButtonStyle(ready)}
          >
            {letterBusy ? '生成中' : ready ? '生成家信' : '记忆不足'}
          </button>
        </div>
      </div>
      {open && (
        sections.length ? (
          <div style={memoryListStyle}>
            {sections.map(section => (
              <div key={section.key} style={memorySectionStyle}>
                <div style={memorySectionTitleStyle}>{section.title}</div>
                <ul style={memoryItemsStyle}>
                  {section.items.map((item, index) => (
                    <li key={`${section.key}-${index}`} style={memoryItemStyle}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <div style={emptyMemoryStyle}>还没有记录到可整理的生命记忆。</div>
        )
      )}
    </section>
  );
}

function LegacyCardPanel({ card, imageUrl, busy }) {
  if (!busy && !imageUrl) return null;
  return (
    <section style={legacyCardPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>传承故事图文卡片</div>
          <div style={subTextStyle}>{imageUrl ? '已生成，可下载图片分享给家人' : '正在整理并生成图文卡片'}</div>
        </div>
        {imageUrl && <a href={imageUrl} download style={downloadLinkStyle}>下载图片</a>}
      </div>
      {busy ? (
        <div style={loadingTextStyle}>正在生成传承故事卡片...</div>
      ) : (
        <div style={legacyPreviewWrapStyle}>
          <img src={imageUrl} alt={card?.title || '传承故事图文卡片'} style={legacyPreviewStyle} />
        </div>
      )}
    </section>
  );
}

function FamilyLetterPanel({ letter, imageUrl, busy }) {
  if (!busy && !imageUrl) return null;
  return (
    <section style={legacyCardPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>写给家人的一封信</div>
          <div style={subTextStyle}>{imageUrl ? '已生成，可下载图片分享给家人' : '正在整理并生成家信'}</div>
        </div>
        {imageUrl && <a href={imageUrl} download style={downloadLinkStyle}>下载图片</a>}
      </div>
      {busy ? (
        <div style={loadingTextStyle}>正在生成家信...</div>
      ) : (
        <div style={legacyPreviewWrapStyle}>
          <img src={imageUrl} alt={letter?.title || '写给家人的一封信'} style={legacyPreviewStyle} />
        </div>
      )}
    </section>
  );
}

function DocumentPanel({ document, documentUrl, busy, confirmBusy, onChange, onConfirm }) {
  if (!busy && !document) return null;
  const canConfirm = !!String(document || '').trim() && !busy && !confirmBusy;
  return (
    <section style={documentPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>人生故事</div>
          <div style={subTextStyle}>
            {documentUrl ? '已保存，可继续修改后再次确认' : '核对后确认保存'}
          </div>
        </div>
        <div style={headActionsStyle}>
          {canConfirm && (
            <button onClick={() => onConfirm(document)} disabled={confirmBusy} style={smallButtonStyle(true)}>
              {confirmBusy ? '保存中' : documentUrl ? '保存修改' : '确认故事'}
            </button>
          )}
          {documentUrl && <a href={documentUrl} download style={downloadLinkStyle}>下载 Word</a>}
        </div>
      </div>
      {busy ? (
        <div style={loadingTextStyle}>正在整理人生故事...</div>
      ) : (
        <textarea
          value={document}
          onChange={e => onChange(e.target.value)}
          style={documentEditorStyle}
        />
      )}
    </section>
  );
}

export default function DignityTherapyPanel({
  status,
  documentBusy,
  documentConfirmBusy,
  document,
  documentUrl,
  legacyCardBusy,
  legacyCard,
  legacyCardImageUrl,
  familyLetterBusy,
  familyLetter,
  familyLetterImageUrl,
  voiceMode,
  onGenerateDocument,
  onGenerateLegacyCard,
  onGenerateFamilyLetter,
  onConfirmDocument,
  onDocumentChange,
  onToggleVoiceMode,
}) {
  const memorySections = collectMemorySections(status?.dignity_memory);
  const memoryItemCount = memorySections.reduce((sum, section) => sum + section.items.length, 0);
  const documentReady = memoryItemCount >= MIN_MEMORY_ITEMS_FOR_DOCUMENT;

  return (
    <div style={screenStyle}>
      <section style={controlPanelStyle}>
        <div style={kickerStyle}>尊严疗法</div>
        <div style={actionsStyle}>
          <button onClick={onToggleVoiceMode} style={primaryButtonStyle(voiceMode)}>
            {voiceMode ? '暂停访谈' : '开始访谈'}
          </button>
        </div>
      </section>

      <MemoryPanel
        sections={memorySections}
        itemCount={memoryItemCount}
        ready={documentReady}
        busy={documentBusy}
        cardBusy={legacyCardBusy}
        letterBusy={familyLetterBusy}
        onGenerateDocument={onGenerateDocument}
        onGenerateLegacyCard={onGenerateLegacyCard}
        onGenerateFamilyLetter={onGenerateFamilyLetter}
      />

      <DocumentPanel
        document={document}
        documentUrl={documentUrl}
        busy={documentBusy}
        confirmBusy={documentConfirmBusy}
        onChange={onDocumentChange}
        onConfirm={onConfirmDocument}
      />

      <LegacyCardPanel
        card={legacyCard}
        imageUrl={legacyCardImageUrl}
        busy={legacyCardBusy}
      />

      <FamilyLetterPanel
        letter={familyLetter}
        imageUrl={familyLetterImageUrl}
        busy={familyLetterBusy}
      />
    </div>
  );
}

const screenStyle = { height: '100%', overflow: 'auto', boxSizing: 'border-box', padding: '34px 30px 30px', color: C.ink, fontFamily: 'Noto Sans SC', display: 'grid', alignContent: 'start', gap: 20 };
const controlPanelStyle = { display: 'grid', gap: 16, padding: '2px 0 18px', borderBottom: `1px solid ${C.mist}22` };
const kickerStyle = { color: C.ink, fontSize: 32, lineHeight: 1.15, fontFamily: 'Noto Serif SC, serif', fontWeight: 600 };
const subTextStyle = { color: C.inkFaint, fontSize: 15, lineHeight: 1.6 };
const actionsStyle = { display: 'flex', flexWrap: 'wrap', gap: 10 };
const primaryButtonStyle = (active) => ({ height: 50, minWidth: 154, padding: '0 24px', borderRadius: 8, border: `1px solid ${active ? C.sage : C.amber}`, background: active ? `linear-gradient(135deg, ${C.sage}, #9fb196)` : `linear-gradient(135deg, ${C.amber}, #d9a85e)`, color: '#fffaf2', fontSize: 16, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: 'pointer', boxShadow: `0 10px 22px ${active ? 'rgba(122,148,128,.24)' : 'rgba(184,130,54,.25)'}` });
const memoryPanelStyle = { padding: '2px 0 22px', borderBottom: `1px solid ${C.mist}22`, display: 'grid', gap: 12 };
const memoryToggleStyle = { height: 40, padding: '0 14px', borderRadius: 8, border: `1px solid ${C.mist}55`, background: 'rgba(255,250,242,.58)', color: C.inkMid, fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: 'Noto Sans SC' };
const memoryCountStyle = { marginLeft: 10, color: C.inkFaint, fontSize: 15, fontFamily: 'Noto Sans SC' };
const generateButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.amber : C.mist}66`, background: enabled ? `${C.amber}22` : 'rgba(255,250,242,.46)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const cardButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.sage : C.mist}66`, background: enabled ? `${C.sage}22` : 'rgba(255,250,242,.46)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const letterButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.green : C.mist}66`, background: enabled ? `${C.green}20` : 'rgba(255,250,242,.46)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const memoryListStyle = { display: 'grid', gap: 12, marginTop: 12 };
const memorySectionStyle = { border: `1px solid ${C.mist}22`, borderRadius: 8, background: 'rgba(255,250,242,.46)', padding: '12px 14px' };
const memorySectionTitleStyle = { color: C.inkMid, fontSize: 15, fontWeight: 600, marginBottom: 8 };
const memoryItemsStyle = { margin: 0, paddingLeft: 18, display: 'grid', gap: 5 };
const memoryItemStyle = { color: C.inkMid, fontSize: 15, lineHeight: 1.65 };
const emptyMemoryStyle = { marginTop: 12, color: C.inkFaint, fontSize: 15, lineHeight: 1.6 };
const documentPanelStyle = { padding: '4px 0 18px', borderBottom: `1px solid ${C.mist}22` };
const legacyCardPanelStyle = { padding: '4px 0 18px', borderBottom: `1px solid ${C.mist}22` };
const sectionHeadStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 };
const headActionsStyle = { display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' };
const sectionTitleStyle = { color: C.ink, fontSize: 20, fontFamily: 'Noto Serif SC, serif', fontWeight: 600 };
const loadingTextStyle = { color: C.inkFaint, fontSize: 15, padding: '12px 0' };
const documentEditorStyle = { width: '100%', minHeight: 330, resize: 'vertical', boxSizing: 'border-box', border: `1px solid ${C.mist}26`, borderRadius: 8, padding: '16px 17px', outline: 'none', color: C.inkMid, background: 'rgba(255,250,242,.84)', fontSize: 16, lineHeight: 1.8, fontFamily: 'Noto Sans SC', boxShadow: 'inset 0 1px 0 rgba(255,255,255,.7)' };
const smallButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.sage : C.mist}66`, background: enabled ? `${C.sage}22` : 'rgba(255,250,242,.52)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap', fontFamily: 'Noto Sans SC' });
const downloadLinkStyle = { display: 'inline-flex', alignItems: 'center', height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${C.amber}88`, color: C.ink, background: `${C.amber}24`, fontSize: 15, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' };
const legacyPreviewWrapStyle = { marginTop: 12, maxWidth: 420, borderRadius: 8, border: `1px solid ${C.mist}26`, background: 'rgba(255,250,242,.64)', overflow: 'hidden' };
const legacyPreviewStyle = { display: 'block', width: '100%', height: 'auto' };
