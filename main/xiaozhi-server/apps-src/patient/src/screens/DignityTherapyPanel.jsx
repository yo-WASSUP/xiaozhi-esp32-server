import { useEffect, useState } from 'react';
import { C } from '../theme';
import RobotAvatar from '../components/RobotAvatar';
import WaveBars from '../components/WaveBars';
import voiceRoomBackground from '../assets/voice/voice-room.webp';
import { getReplyDensity } from '../utils/replyText';

const MIN_MEMORY_ITEMS_FOR_DOCUMENT = 6;

const MEMORY_LABELS = {
  life_story_materials: '人生经历',
  important_relationships: '重要关系',
  values_and_strengths: '珍视与力量',
  messages_to_family: '给家人的话',
};

const LETTER_TEMPLATES = [
  { id: 'warm', name: '暖黄', swatch: '#e8c98f', preview: './images/letter_templates/warm.png', envelope: './images/letter_templates/envelope-warm.png' },
  { id: 'floral', name: '花影', swatch: '#e7a7b0', preview: './images/letter_templates/floral.png', envelope: './images/letter_templates/envelope-floral.png' },
  { id: 'bamboo', name: '青竹', swatch: '#9fbd94', preview: './images/letter_templates/bamboo.png', envelope: './images/letter_templates/envelope-bamboo.png' },
  { id: 'sky', name: '晴空', swatch: '#9fc5df', preview: './images/letter_templates/sky.png', envelope: './images/letter_templates/envelope-sky.png' },
  { id: 'plain', name: '素白', swatch: '#f4ecdd', preview: './images/letter_templates/plain.png', envelope: './images/letter_templates/envelope-plain.png' },
];

function DignityInterviewStage({
  aiState,
  msg,
  openingReply,
  lastHeard,
  connected,
  recording,
  userSpeaking,
  inputLevel,
  outputLevel,
  voiceMode,
  paused,
}) {
  const passiveState = aiState === 'speaking' || aiState === 'thinking' ? aiState : 'idle';
  const displayState = voiceMode && aiState === 'idle' && connected && recording && userSpeaking
    ? 'listening'
    : voiceMode
      ? aiState
      : passiveState;
  const activitySource = userSpeaking || aiState !== 'speaking' ? 'input' : 'output';
  const activityLevel = activitySource === 'input' ? inputLevel : outputLevel;
  const statusText = !connected
    ? '语音服务连接中'
    : paused
      ? '访谈已暂停'
    : voiceMode
      ? (userSpeaking ? '正在听您说' : '访谈进行中')
      : '访谈已暂停';
  const fallbackReply = !connected
    ? '语音服务正在连接，请稍等一会儿。'
    : paused
      ? '我们已经暂停。您想继续时，可以对我说“继续访谈”。'
    : voiceMode
      ? '我在这里。我们可以慢慢聊，您想到什么就说什么。'
      : '访谈已暂停，准备好后可以继续。';
  const reply = msg || openingReply || fallbackReply;
  const replyDensity = getReplyDensity(reply);

  return (
    <aside
      className={`dignity-interview dignity-interview--${displayState} dignity-interview--reply-${replyDensity}${paused ? ' dignity-interview--paused' : ''}`}
      style={{ '--dignity-room-background': `url(${voiceRoomBackground})` }}
      aria-label="尊严疗法实时语音访谈"
    >
      <div className="dignity-interview__header">
        <div>
          <span className="dignity-interview__eyebrow">实时语音访谈</span>
          <h2>和小暖慢慢聊</h2>
        </div>
        <span className={`dignity-interview__status ${voiceMode && !paused ? 'is-active' : ''}`}>
          <i aria-hidden="true" />
          {statusText}
        </span>
      </div>

      <div className="dignity-interview__avatar" aria-hidden="true">
        <RobotAvatar state={displayState} />
      </div>

      <div className="dignity-interview__conversation" aria-live="polite">
        <div className="dignity-interview__turn dignity-interview__turn--user">
          <span>您说</span>
          <p className={lastHeard ? '' : 'is-quiet'}>
            {lastHeard || '您说的话会显示在这里'}
          </p>
        </div>
        <div className="dignity-interview__turn dignity-interview__turn--assistant">
          <span>小暖</span>
          <p className={`dignity-interview__reply-text dignity-interview__reply-text--${replyDensity}${(msg || openingReply) ? '' : ' is-quiet'}`}>{reply}</p>
        </div>
      </div>

      <div className="dignity-interview__activity" aria-hidden="true">
        <WaveBars
          source={activitySource}
          level={activityLevel}
          active={!paused && connected && ((voiceMode && recording) || aiState === 'speaking')}
        />
      </div>
    </aside>
  );
}

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

function memoryItemText(item) {
  if (typeof item === 'string') return item.trim();
  if (item && typeof item === 'object') {
    return Object.values(item).filter(Boolean).map(value => String(value).trim()).filter(Boolean).join(' ');
  }
  return String(item || '').trim();
}

function memoryToDraft(memory) {
  return Object.keys(MEMORY_LABELS).reduce((draft, key) => {
    const items = Array.isArray(memory?.[key]) ? memory[key] : [];
    draft[key] = items.map(memoryItemText).filter(Boolean);
    return draft;
  }, {});
}

function MemoryPanel({
  memory,
  itemCount,
  busy,
  onSave,
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => memoryToDraft(memory));
  const sections = collectMemorySections(memory);

  useEffect(() => {
    if (!editing) setDraft(memoryToDraft(memory));
  }, [memory, editing]);

  const beginEditing = () => {
    setDraft(memoryToDraft(memory));
    setOpen(true);
    setEditing(true);
  };
  const cancelEditing = () => {
    setDraft(memoryToDraft(memory));
    setEditing(false);
  };
  const updateItem = (key, index, value) => {
    setDraft(current => ({
      ...current,
      [key]: current[key].map((item, itemIndex) => (itemIndex === index ? value : item)),
    }));
  };
  const removeItem = (key, index) => {
    setDraft(current => ({
      ...current,
      [key]: current[key].filter((_, itemIndex) => itemIndex !== index),
    }));
  };
  const addItem = (key) => {
    setDraft(current => ({ ...current, [key]: [...current[key], ''] }));
  };
  const save = async () => {
    const nextMemory = Object.keys(MEMORY_LABELS).reduce((result, key) => {
      result[key] = draft[key].map(item => item.trim()).filter(Boolean);
      return result;
    }, {});
    const ok = await onSave(nextMemory);
    if (ok) setEditing(false);
  };

  return (
    <section style={memoryPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <span style={sectionTitleStyle}>生命记忆</span>
          <span style={memoryCountStyle}>{itemCount} 条</span>
          <div style={subTextStyle}>访谈会自动整理，您也可以补充、修改或删除。</div>
        </div>
        <div style={headActionsStyle}>
          {!editing && (
            <button type="button" onClick={() => setOpen(value => !value)} style={memoryToggleStyle}>
              {open ? '收起' : '查看全部'}
            </button>
          )}
          {!editing && <button type="button" onClick={beginEditing} style={smallButtonStyle(true)}>编辑记忆</button>}
        </div>
      </div>
      {editing ? (
        <div className="dignity-memory-editor" style={memoryEditorStyle}>
          {Object.entries(MEMORY_LABELS).map(([key, title]) => (
            <section key={key} style={memoryEditorSectionStyle}>
              <div style={memoryEditorSectionHeadStyle}>
                <div>
                  <div style={memorySectionTitleStyle}>{title}</div>
                  <div style={memoryEditorHintStyle}>{draft[key].length} 条</div>
                </div>
                <button type="button" onClick={() => addItem(key)} style={textActionButtonStyle}>添加一条</button>
              </div>
              {draft[key].length ? (
                <div style={memoryEditorItemsStyle}>
                  {draft[key].map((item, index) => (
                    <div key={`${key}-${index}`} style={memoryEditorItemStyle}>
                      <label htmlFor={`memory-${key}-${index}`} style={editorLabelStyle}>记忆 {index + 1}</label>
                      <textarea
                        id={`memory-${key}-${index}`}
                        value={item}
                        onChange={event => updateItem(key, index, event.target.value)}
                        rows={2}
                        style={memoryTextareaStyle}
                      />
                      <button type="button" onClick={() => removeItem(key, index)} style={removeMemoryButtonStyle}>删除</button>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={memoryEditorEmptyStyle}>这一类还没有内容，可以手动添加。</div>
              )}
            </section>
          ))}
          <div style={memoryEditorActionsStyle}>
            <button type="button" onClick={cancelEditing} disabled={busy} style={memoryToggleStyle}>取消</button>
            <button type="button" onClick={save} disabled={busy} style={saveMemoryButtonStyle(!busy)}>
              {busy ? '保存中' : '保存生命记忆'}
            </button>
          </div>
        </div>
      ) : open && (
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

function ArtifactLauncherPanel({
  ready,
  document,
  documentUrl,
  documentBusy,
  card,
  cardImageUrl,
  cardBusy,
  onGenerateDocument,
  onGenerateLegacyCard,
}) {
  const disabledHint = `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`;
  return (
    <section style={artifactLauncherStyle}>
      <div>
        <div style={sectionTitleStyle}>整理成果</div>
        <div style={subTextStyle}>生命记忆确认后，再整理人生故事或传承卡片。</div>
      </div>
      <div className="dignity-artifact-grid" style={artifactGridStyle}>
        <article className="dignity-artifact-action" style={artifactActionStyle}>
          <div>
            <div style={artifactTitleStyle}>人生故事</div>
            <div style={artifactDescriptionStyle}>
              {documentUrl ? '故事已确认保存，可继续修改。' : document ? '已有故事草稿，您可以继续编辑。' : '整理为一篇可编辑、可下载的人生故事。'}
            </div>
          </div>
          <button
            type="button"
            onClick={onGenerateDocument}
            disabled={documentBusy || !ready}
            title={ready ? '' : disabledHint}
            style={artifactPrimaryButtonStyle(!documentBusy && ready)}
          >
            {documentBusy ? '正在整理' : document ? '重新整理' : ready ? '生成人生故事' : '记忆不足'}
          </button>
        </article>
        <article className="dignity-artifact-action" style={artifactActionStyle}>
          <div>
            <div style={artifactTitleStyle}>传承卡片</div>
            <div style={artifactDescriptionStyle}>
              {cardImageUrl ? '卡片已经生成，可编辑或下载分享。' : card ? '卡片内容已生成，等待图片完成。' : '把重要片段整理成便于保存和分享的图文卡片。'}
            </div>
          </div>
          <button
            type="button"
            onClick={onGenerateLegacyCard}
            disabled={cardBusy || !ready}
            title={ready ? '' : disabledHint}
            style={artifactSecondaryButtonStyle(!cardBusy && ready)}
          >
            {cardBusy ? '生成中' : card || cardImageUrl ? '重新生成' : ready ? '生成传承卡片' : '记忆不足'}
          </button>
        </article>
      </div>
    </section>
  );
}

function ReadButton({ active, disabled, onRead, onStop }) {
  return (
    <button
      type="button"
      onClick={active ? onStop : onRead}
      disabled={disabled && !active}
      style={readButtonStyle(active, !(disabled && !active))}
    >
      {active ? '停止朗读' : '朗读'}
    </button>
  );
}

function LegacyCardPanel({ card, imageUrl, busy, reading, onRead, onStopReading, onChange, onSave }) {
  const [editing, setEditing] = useState(false);
  if (!busy && !imageUrl && !card) return null;
  const canRead = !!card && !busy;
  const sections = Array.isArray(card?.sections) ? card.sections : [];
  const updateCard = (patch) => onChange({ ...(card || {}), ...patch });
  const updateSection = (index, patch) => {
    updateCard({
      sections: sections.map((section, i) => (i === index ? { ...section, ...patch } : section)),
    });
  };
  const removeSection = (index) => {
    updateCard({ sections: sections.filter((_, i) => i !== index) });
  };
  const addSection = () => {
    updateCard({
      sections: [...sections, { title: '新的片段', body: '', quote: '' }],
    });
  };
  return (
    <section style={legacyCardPanelStyle}>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>传承故事图文卡片</div>
          <div style={subTextStyle}>{imageUrl ? '已生成，可下载图片分享给家人' : '正在整理并生成图文卡片'}</div>
        </div>
        <div style={headActionsStyle}>
          <ReadButton active={reading} disabled={!canRead} onRead={onRead} onStop={onStopReading} />
          {card && <button onClick={() => setEditing(value => !value)} disabled={busy} style={smallButtonStyle(true)}>{editing ? '完成编辑' : '编辑'}</button>}
          {editing && card && <button onClick={() => onSave(card).then(() => setEditing(false))} disabled={busy} style={smallButtonStyle(true)}>{busy ? '保存中' : '保存卡片'}</button>}
          {imageUrl && <a href={imageUrl} download style={downloadLinkStyle}>下载图片</a>}
        </div>
      </div>
      {busy ? (
        <div style={loadingTextStyle}>正在生成传承故事卡片...</div>
      ) : (
        <>
          {editing && card && (
            <div style={editorPanelStyle}>
              <input value={card.title || ''} onChange={e => updateCard({ title: e.target.value })} style={fieldStyle} placeholder="卡片标题" />
              <input value={card.subtitle || ''} onChange={e => updateCard({ subtitle: e.target.value })} style={fieldStyle} placeholder="副标题" />
              <textarea value={card.intro || ''} onChange={e => updateCard({ intro: e.target.value })} rows={3} style={textareaFieldStyle} placeholder="开篇文字" />
              {sections.map((section, index) => (
                <div key={index} style={nestedEditorStyle}>
                  <div style={sectionEditorHeadStyle}>
                    <span style={editorLabelStyle}>片段 {index + 1}</span>
                    <button type="button" onClick={() => removeSection(index)} style={textButtonStyle}>删除</button>
                  </div>
                  <input value={section.title || ''} onChange={e => updateSection(index, { title: e.target.value })} style={fieldStyle} placeholder="片段标题" />
                  <textarea value={section.body || ''} onChange={e => updateSection(index, { body: e.target.value })} rows={3} style={textareaFieldStyle} placeholder="片段正文" />
                  <input value={section.quote || ''} onChange={e => updateSection(index, { quote: e.target.value })} style={fieldStyle} placeholder="引用/金句" />
                </div>
              ))}
              <button type="button" onClick={addSection} style={smallButtonStyle(true)}>添加片段</button>
              <textarea value={card.wish || ''} onChange={e => updateCard({ wish: e.target.value })} rows={2} style={textareaFieldStyle} placeholder="最大的心愿" />
              <input value={card.closing || ''} onChange={e => updateCard({ closing: e.target.value })} style={fieldStyle} placeholder="结尾落款" />
            </div>
          )}
          {imageUrl && (
            <div style={legacyPreviewWrapStyle}>
              <img src={imageUrl} alt={card?.title || '传承故事图文卡片'} style={legacyPreviewStyle} />
            </div>
          )}
        </>
      )}
    </section>
  );
}

function FamilyLetterPanel({ letter, imageUrl, busy, ready, reading, template, onTemplateChange, onGenerate, onRead, onStopReading, onChange, onSave }) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const canRead = !!letter && !busy;
  const selectedTemplate = LETTER_TEMPLATES.find(item => item.id === template) || LETTER_TEMPLATES[0];
  const paragraphs = Array.isArray(letter?.paragraphs) ? letter.paragraphs : [];
  const updateLetter = (patch) => onChange({ ...(letter || {}), ...patch });
  const updateParagraph = (index, value) => {
    updateLetter({ paragraphs: paragraphs.map((paragraph, i) => (i === index ? value : paragraph)) });
  };
  const removeParagraph = (index) => {
    updateLetter({ paragraphs: paragraphs.filter((_, i) => i !== index) });
  };
  const addParagraph = () => {
    updateLetter({ paragraphs: [...paragraphs, ''] });
  };

  if (!letter && !imageUrl) {
    return (
      <section className="dignity-compact-letter" style={compactLetterPanelStyle}>
        <div>
          <div style={sectionTitleStyle}>写给家人的一封信</div>
          <div style={subTextStyle}>
            {busy ? '正在根据生命记忆整理家信，请稍候。' : '准备好后，再把想说的话整理成一封家信。'}
          </div>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={busy || !ready}
          title={ready ? '' : `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`}
          style={artifactSecondaryButtonStyle(!busy && ready)}
        >
          {busy ? '正在生成' : ready ? '生成家信' : '记忆不足'}
        </button>
      </section>
    );
  }

  return (
    <section style={legacyCardPanelStyle}>
      <style>{letterAnimationCss}</style>
      <div style={sectionHeadStyle}>
        <div>
          <div style={sectionTitleStyle}>写给家人的一封信</div>
          <div style={subTextStyle}>{imageUrl ? `已装入${selectedTemplate.name}信封，点击信封查看` : '家信内容已经整理完成'}</div>
        </div>
        <div style={headActionsStyle}>
          {open && <ReadButton active={reading} disabled={!canRead} onRead={onRead} onStop={onStopReading} />}
          {open && letter && <button onClick={() => setEditing(value => !value)} disabled={busy} style={smallButtonStyle(true)}>{editing ? '完成编辑' : '编辑'}</button>}
          {open && editing && letter && <button onClick={() => onSave(letter).then(() => setEditing(false))} disabled={busy} style={smallButtonStyle(true)}>{busy ? '保存中' : '保存家信'}</button>}
          {open && imageUrl && <a href={imageUrl} download style={downloadLinkStyle}>下载图片</a>}
        </div>
      </div>
      <div style={templatePanelStyle}>
        <div style={templateLabelStyle}>家信信纸</div>
        <div style={templateGridStyle}>
          {LETTER_TEMPLATES.map(item => (
            <button
              key={item.id}
              type="button"
              onClick={() => onTemplateChange(item.id)}
              style={templateButtonStyle(template === item.id)}
            >
              <span style={{ ...templateSwatchStyle, backgroundImage: `url(${item.preview})` }} />
              {item.name}
            </button>
          ))}
        </div>
        <button
          onClick={onGenerate}
          disabled={busy || !ready}
          title={ready ? '' : `至少需要 ${MIN_MEMORY_ITEMS_FOR_DOCUMENT} 条生命记忆`}
          style={letterTemplateGenerateStyle(!busy && ready)}
        >
          {busy ? '生成中' : ready ? (letter ? '按此信纸重新生成' : '生成家信') : '记忆不足'}
        </button>
      </div>
      {busy ? (
        <div style={loadingTextStyle}>正在更新家信...</div>
      ) : !open ? (
        <button type="button" onClick={() => setOpen(true)} style={envelopeStyle(selectedTemplate.swatch, selectedTemplate.envelope)}>
          <span style={envelopeLinerStyle(selectedTemplate.swatch, selectedTemplate.preview)} />
          <span style={envelopeFlapStyle} />
          <span style={envelopeLeftFoldStyle} />
          <span style={envelopeRightFoldStyle} />
          <span style={envelopeAddressStyle}>
            <span style={envelopeAddressLineStyle} />
            <span style={envelopeAddressLineStyle} />
            <span style={{ ...envelopeAddressLineStyle, width: 96 }} />
          </span>
          <span style={envelopeStampStyle(selectedTemplate.swatch)} />
          <span style={envelopeSealStyle(selectedTemplate.swatch)} />
          <span style={envelopeTitleStyle}>给家人的一封信</span>
          <span style={envelopeHintStyle}>轻触打开</span>
        </button>
      ) : (
        <>
          <button type="button" onClick={() => { setOpen(false); setEditing(false); }} style={closeEnvelopeButtonStyle}>收起信封</button>
          {editing && letter && (
            <div style={editorPanelStyle}>
              <input value={letter.title || ''} onChange={e => updateLetter({ title: e.target.value })} style={fieldStyle} placeholder="家信标题" />
              <input value={letter.subtitle || ''} onChange={e => updateLetter({ subtitle: e.target.value })} style={fieldStyle} placeholder="副标题" />
              <input value={letter.salutation || ''} onChange={e => updateLetter({ salutation: e.target.value })} style={fieldStyle} placeholder="称呼" />
              {paragraphs.map((paragraph, index) => (
                <div key={index} style={nestedEditorStyle}>
                  <div style={sectionEditorHeadStyle}>
                    <span style={editorLabelStyle}>正文 {index + 1}</span>
                    <button type="button" onClick={() => removeParagraph(index)} style={textButtonStyle}>删除</button>
                  </div>
                  <textarea value={paragraph || ''} onChange={e => updateParagraph(index, e.target.value)} rows={4} style={textareaFieldStyle} placeholder="家信正文" />
                </div>
              ))}
              <button type="button" onClick={addParagraph} style={smallButtonStyle(true)}>添加正文</button>
              <input value={letter.signature || ''} onChange={e => updateLetter({ signature: e.target.value })} style={fieldStyle} placeholder="署名" />
              <input value={letter.date || ''} onChange={e => updateLetter({ date: e.target.value })} style={fieldStyle} placeholder="日期" />
            </div>
          )}
          <div style={letterRevealStageStyle}>
            <div style={openedEnvelopeStyle(selectedTemplate.swatch, selectedTemplate.envelope)}>
              <span style={openedEnvelopeBackStyle(selectedTemplate.swatch, selectedTemplate.preview)} />
              <span style={openedEnvelopeFlapStyle(selectedTemplate.swatch, selectedTemplate.envelope)} />
              <span style={openedEnvelopePocketStyle(selectedTemplate.swatch, selectedTemplate.envelope)} />
              <span style={openedEnvelopeSealStyle(selectedTemplate.swatch)} />
            </div>
            <div style={revealedLetterFrameStyle}>
              <img src={imageUrl} alt={letter?.title || '写给家人的一封信'} style={revealedLetterImageStyle} />
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function DocumentPanel({ document, documentUrl, busy, confirmBusy, reading, onChange, onConfirm, onRead, onStopReading }) {
  if (!busy && !document) return null;
  const canConfirm = !!String(document || '').trim() && !busy && !confirmBusy;
  const canRead = !!String(document || '').trim() && !busy;
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
          <ReadButton active={reading} disabled={!canRead} onRead={onRead} onStop={onStopReading} />
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
  aiState,
  msg,
  lastHeard,
  connected,
  recording,
  userSpeaking,
  inputLevel = 0,
  outputLevel = 0,
  openingReply,
  documentBusy,
  documentConfirmBusy,
  memoryBusy,
  document,
  documentUrl,
  legacyCardBusy,
  legacyCard,
  legacyCardImageUrl,
  familyLetterBusy,
  familyLetter,
  familyLetterImageUrl,
  voiceMode,
  paused,
  onGenerateDocument,
  onGenerateLegacyCard,
  onGenerateFamilyLetter,
  onLegacyCardChange,
  onSaveLegacyCard,
  familyLetterTemplate,
  onFamilyLetterTemplateChange,
  onFamilyLetterChange,
  onSaveFamilyLetter,
  onConfirmDocument,
  onDocumentChange,
  onSaveMemory,
  onToggleVoiceMode,
  readingKind,
  onReadDocument,
  onReadLegacyCard,
  onReadFamilyLetter,
  onStopReading,
}) {
  const memorySections = collectMemorySections(status?.dignity_memory);
  const memoryItemCount = memorySections.reduce((sum, section) => sum + section.items.length, 0);
  const documentReady = memoryItemCount >= MIN_MEMORY_ITEMS_FOR_DOCUMENT;

  return (
    <div className="dignity-therapy">
      <DignityInterviewStage
        aiState={aiState}
        msg={msg}
        openingReply={openingReply}
        lastHeard={lastHeard}
        connected={connected}
        recording={recording}
        userSpeaking={userSpeaking}
        inputLevel={inputLevel}
        outputLevel={outputLevel}
        voiceMode={voiceMode}
        paused={paused}
      />

      <main className="dignity-therapy__workspace">
        <section style={controlPanelStyle}>
          <div style={kickerStyle}>尊严疗法</div>
          <div style={actionsStyle}>
            <button onClick={onToggleVoiceMode} style={primaryButtonStyle(voiceMode && !paused)}>
              {paused ? '继续访谈' : voiceMode ? '暂停访谈' : '开始访谈'}
            </button>
          </div>
        </section>

        <MemoryPanel
          memory={status?.dignity_memory || {}}
          itemCount={memoryItemCount}
          busy={memoryBusy}
          onSave={onSaveMemory}
        />

        <ArtifactLauncherPanel
          ready={documentReady}
          document={document}
          documentUrl={documentUrl}
          documentBusy={documentBusy}
          card={legacyCard}
          cardImageUrl={legacyCardImageUrl}
          cardBusy={legacyCardBusy}
          onGenerateDocument={onGenerateDocument}
          onGenerateLegacyCard={onGenerateLegacyCard}
        />

        <DocumentPanel
          document={document}
          documentUrl={documentUrl}
          busy={documentBusy}
          confirmBusy={documentConfirmBusy}
          reading={readingKind === 'document'}
          onChange={onDocumentChange}
          onConfirm={onConfirmDocument}
          onRead={onReadDocument}
          onStopReading={onStopReading}
        />

        <LegacyCardPanel
          card={legacyCard}
          imageUrl={legacyCardImageUrl}
          busy={legacyCardBusy}
          reading={readingKind === 'card'}
          onRead={onReadLegacyCard}
          onStopReading={onStopReading}
          onChange={onLegacyCardChange}
          onSave={onSaveLegacyCard}
        />

        <FamilyLetterPanel
          letter={familyLetter}
          imageUrl={familyLetterImageUrl}
          busy={familyLetterBusy}
          ready={documentReady}
          reading={readingKind === 'letter'}
          template={familyLetterTemplate}
          onTemplateChange={onFamilyLetterTemplateChange}
          onGenerate={onGenerateFamilyLetter}
          onRead={onReadFamilyLetter}
          onStopReading={onStopReading}
          onChange={onFamilyLetterChange}
          onSave={onSaveFamilyLetter}
        />
      </main>
    </div>
  );
}

const controlPanelStyle = { display: 'grid', gap: 16, padding: '2px 0 18px', borderBottom: `1px solid ${C.mist}22` };
const kickerStyle = { color: C.ink, fontSize: 32, lineHeight: 1.15, fontFamily: 'Noto Serif SC, serif', fontWeight: 600 };
const subTextStyle = { color: C.inkFaint, fontSize: 15, lineHeight: 1.6 };
const actionsStyle = { display: 'flex', flexWrap: 'wrap', gap: 10 };
const primaryButtonStyle = (active) => ({ height: 50, minWidth: 154, padding: '0 24px', borderRadius: 8, border: `1px solid ${active ? C.sage : C.amber}`, background: active ? `linear-gradient(135deg, ${C.sage}, #9fb196)` : `linear-gradient(135deg, ${C.amber}, #d9a85e)`, color: '#fffaf2', fontSize: 16, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: 'pointer', boxShadow: `0 10px 22px ${active ? 'rgba(122,148,128,.24)' : 'rgba(184,130,54,.25)'}` });
const memoryPanelStyle = { padding: '2px 0 22px', borderBottom: `1px solid ${C.mist}22`, display: 'grid', gap: 12 };
const memoryToggleStyle = { height: 40, padding: '0 14px', borderRadius: 8, border: `1px solid ${C.mist}55`, background: 'rgba(255,250,242,.58)', color: C.inkMid, fontSize: 15, fontWeight: 600, whiteSpace: 'nowrap', cursor: 'pointer', fontFamily: 'Noto Sans SC' };
const memoryCountStyle = { marginLeft: 10, color: C.inkFaint, fontSize: 15, fontFamily: 'Noto Sans SC' };
const memoryEditorStyle = { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, padding: 14, border: `1px solid ${C.mist}33`, borderRadius: 12, background: 'rgba(255,250,242,.5)' };
const memoryEditorSectionStyle = { minWidth: 0, display: 'grid', alignContent: 'start', gap: 10, padding: 12, borderRadius: 10, border: `1px solid ${C.mist}22`, background: 'rgba(255,254,250,.86)' };
const memoryEditorSectionHeadStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 };
const memoryEditorHintStyle = { marginTop: 2, color: C.inkFaint, fontSize: 12 };
const memoryEditorItemsStyle = { display: 'grid', gap: 10 };
const memoryEditorItemStyle = { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 7, alignItems: 'end' };
const memoryTextareaStyle = { gridColumn: '1 / -1', width: '100%', minHeight: 64, boxSizing: 'border-box', resize: 'vertical', borderRadius: 8, border: `1px solid ${C.mist}44`, padding: '9px 10px', outline: 'none', background: '#fffefa', color: C.inkMid, fontSize: 14, lineHeight: 1.55, fontFamily: 'Noto Sans SC' };
const memoryEditorEmptyStyle = { padding: '10px 0', color: C.inkFaint, fontSize: 13, lineHeight: 1.6 };
const memoryEditorActionsStyle = { gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 2 };
const textActionButtonStyle = { height: 34, padding: '0 11px', borderRadius: 8, border: `1px solid ${C.sage}55`, background: `${C.sage}12`, color: C.sage, fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'Noto Sans SC', whiteSpace: 'nowrap' };
const removeMemoryButtonStyle = { justifySelf: 'end', border: 0, background: 'transparent', color: C.red, padding: 0, fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer' };
const saveMemoryButtonStyle = (enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.sage : C.mist}66`, background: enabled ? C.sage : 'rgba(130,154,144,.18)', color: enabled ? '#fffaf2' : C.inkFaint, fontSize: 15, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const artifactLauncherStyle = { display: 'grid', gap: 12, padding: '2px 0 22px', borderBottom: `1px solid ${C.mist}22` };
const artifactGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 };
const artifactActionStyle = { minWidth: 0, minHeight: 116, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, padding: '15px 16px', borderRadius: 12, border: `1px solid ${C.mist}2f`, background: 'rgba(255,250,242,.62)' };
const artifactTitleStyle = { color: C.ink, fontSize: 17, fontWeight: 700, fontFamily: 'Noto Sans SC' };
const artifactDescriptionStyle = { maxWidth: 330, marginTop: 5, color: C.inkFaint, fontSize: 13, lineHeight: 1.55 };
const artifactPrimaryButtonStyle = (enabled) => ({ flex: '0 0 auto', height: 40, padding: '0 15px', borderRadius: 8, border: `1px solid ${enabled ? C.amber : C.mist}66`, background: enabled ? C.amber : 'rgba(130,154,144,.14)', color: enabled ? '#fffaf2' : C.inkFaint, fontSize: 14, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const artifactSecondaryButtonStyle = (enabled) => ({ flex: '0 0 auto', height: 40, padding: '0 15px', borderRadius: 8, border: `1px solid ${enabled ? C.sage : C.mist}66`, background: enabled ? C.sage : 'rgba(130,154,144,.14)', color: enabled ? '#fffaf2' : C.inkFaint, fontSize: 14, fontWeight: 700, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
const compactLetterPanelStyle = { minHeight: 84, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, padding: '15px 16px', borderRadius: 12, border: `1px solid ${C.mist}2f`, background: 'rgba(255,250,242,.62)', marginBottom: 18 };
const templatePanelStyle = { display: 'grid', gap: 8, padding: '10px 12px', border: `1px solid ${C.mist}22`, borderRadius: 8, background: 'rgba(255,250,242,.42)' };
const templateLabelStyle = { color: C.inkMid, fontSize: 14, fontWeight: 700 };
const templateGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(5, minmax(82px, 1fr))', gap: 8 };
const templateButtonStyle = (active) => ({ minHeight: 78, minWidth: 0, display: 'grid', alignContent: 'center', justifyItems: 'center', gap: 6, borderRadius: 8, border: `1px solid ${active ? C.green : C.mist}66`, background: active ? `${C.green}18` : 'rgba(255,250,242,.74)', color: active ? C.ink : C.inkMid, fontSize: 14, fontWeight: active ? 700 : 500, fontFamily: 'Noto Sans SC', cursor: 'pointer', whiteSpace: 'nowrap' });
const templateSwatchStyle = { width: 46, height: 34, borderRadius: 4, border: `1px solid ${C.mist}77`, flex: '0 0 auto', backgroundSize: 'cover', backgroundPosition: 'center', boxShadow: '0 4px 10px rgba(40,28,16,.12)' };
const letterTemplateGenerateStyle = (enabled) => ({ height: 40, justifySelf: 'start', padding: '0 16px', borderRadius: 8, border: `1px solid ${enabled ? C.green : C.mist}66`, background: enabled ? `${C.green}22` : 'rgba(255,250,242,.52)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, fontFamily: 'Noto Sans SC', cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' });
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
const readButtonStyle = (active, enabled) => ({ height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${active ? C.green : enabled ? C.sage : C.mist}66`, background: active ? `${C.green}24` : enabled ? `${C.sage}20` : 'rgba(255,250,242,.52)', color: enabled ? C.ink : C.inkFaint, fontSize: 15, fontWeight: enabled ? 700 : 500, cursor: enabled ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap', fontFamily: 'Noto Sans SC' });
const downloadLinkStyle = { display: 'inline-flex', alignItems: 'center', height: 40, padding: '0 16px', borderRadius: 8, border: `1px solid ${C.amber}88`, color: C.ink, background: `${C.amber}24`, fontSize: 15, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' };
const legacyPreviewWrapStyle = { marginTop: 12, maxWidth: 420, borderRadius: 8, border: `1px solid ${C.mist}26`, background: 'rgba(255,250,242,.64)', overflow: 'hidden' };
const legacyPreviewStyle = { display: 'block', width: '100%', height: 'auto' };
const editorPanelStyle = { display: 'grid', gap: 10, maxWidth: 620, padding: 12, border: `1px solid ${C.mist}22`, borderRadius: 8, background: 'rgba(255,250,242,.46)', marginTop: 10 };
const fieldStyle = { width: '100%', boxSizing: 'border-box', height: 40, borderRadius: 8, border: `1px solid ${C.mist}33`, background: 'rgba(255,250,242,.86)', color: C.inkMid, padding: '0 12px', outline: 'none', fontSize: 15, fontFamily: 'Noto Sans SC' };
const textareaFieldStyle = { ...fieldStyle, height: 'auto', minHeight: 86, padding: '10px 12px', resize: 'vertical', lineHeight: 1.6 };
const nestedEditorStyle = { display: 'grid', gap: 8, padding: 10, borderRadius: 8, border: `1px solid ${C.mist}22`, background: 'rgba(255,250,242,.58)' };
const sectionEditorHeadStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 };
const editorLabelStyle = { color: C.inkMid, fontSize: 14, fontWeight: 700 };
const textButtonStyle = { border: 0, background: 'transparent', color: C.red, fontSize: 13, fontFamily: 'Noto Sans SC', cursor: 'pointer', padding: 0 };
const envelopeStyle = (accent, image) => ({ position: 'relative', width: 'min(500px, 100%)', aspectRatio: '1.5 / 1', border: `1px solid ${C.mist}55`, borderRadius: 8, backgroundImage: `linear-gradient(180deg, rgba(255,250,242,.08), rgba(60,38,18,.08)), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center', overflow: 'hidden', cursor: 'pointer', boxShadow: '0 18px 34px rgba(30,24,16,.18), inset 0 1px 0 rgba(255,255,255,.88)', fontFamily: 'Noto Sans SC', color: C.ink, display: 'grid', placeItems: 'center', marginTop: 10 });
const envelopeLinerStyle = (accent, image) => ({ position: 'absolute', left: 18, right: 18, top: 12, height: '38%', clipPath: 'polygon(0 0, 100% 0, 50% 100%)', backgroundImage: `linear-gradient(180deg, rgba(255,250,242,.55), ${accent}1f), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center top', borderRadius: '0 0 8px 8px', opacity: .9, filter: 'saturate(.92) brightness(1.03)' });
const envelopeFlapStyle = { position: 'absolute', left: 0, right: 0, top: 0, height: '58%', clipPath: 'polygon(0 0, 100% 0, 50% 100%)', background: 'linear-gradient(180deg, rgba(255,252,246,.18), rgba(92,63,35,.1))', borderBottom: `1px solid ${C.mist}44`, boxShadow: '0 8px 20px rgba(58,45,28,.08)' };
const envelopeLeftFoldStyle = { position: 'absolute', left: 0, bottom: 0, width: '52%', height: '64%', clipPath: 'polygon(0 0, 100% 100%, 0 100%)', background: 'linear-gradient(35deg, rgba(255,250,242,.18), rgba(86,58,30,.09))', borderTop: `1px solid ${C.mist}33` };
const envelopeRightFoldStyle = { position: 'absolute', right: 0, bottom: 0, width: '52%', height: '64%', clipPath: 'polygon(100% 0, 0 100%, 100% 100%)', background: 'linear-gradient(325deg, rgba(255,250,242,.16), rgba(86,58,30,.08))', borderTop: `1px solid ${C.mist}33` };
const envelopeAddressStyle = { position: 'absolute', left: 32, bottom: 36, display: 'grid', gap: 8, width: 150, opacity: .44 };
const envelopeAddressLineStyle = { display: 'block', width: 136, height: 2, borderRadius: 999, background: C.inkMid };
const envelopeStampStyle = (accent) => ({ position: 'absolute', top: 26, right: 28, width: 54, height: 44, borderRadius: 6, border: `2px solid ${accent}`, background: `linear-gradient(135deg, rgba(255,250,242,.74), ${accent}28)`, boxShadow: 'inset 0 0 0 3px rgba(255,250,242,.72)' });
const envelopeSealStyle = (accent) => ({ position: 'absolute', top: '43%', left: '50%', width: 50, height: 50, transform: 'translate(-50%, -50%)', borderRadius: 999, background: `radial-gradient(circle at 35% 30%, #fffaf2 0 7%, ${accent} 24%, ${accent} 100%)`, border: '3px solid rgba(255,250,242,.94)', boxShadow: '0 7px 16px rgba(30,24,16,.2)' });
const envelopeTitleStyle = { position: 'relative', zIndex: 1, marginTop: 52, fontSize: 22, fontFamily: 'Noto Serif SC, serif', fontWeight: 600, letterSpacing: 0, padding: '5px 16px', borderRadius: 8, background: 'rgba(255,250,242,.56)', boxShadow: '0 1px 0 rgba(255,255,255,.65)' };
const envelopeHintStyle = { position: 'absolute', bottom: 22, left: 0, right: 0, textAlign: 'center', color: C.inkFaint, fontSize: 14 };
const closeEnvelopeButtonStyle = { height: 36, padding: '0 14px', borderRadius: 8, border: `1px solid ${C.mist}66`, background: 'rgba(255,250,242,.72)', color: C.inkMid, fontSize: 14, fontWeight: 600, fontFamily: 'Noto Sans SC', cursor: 'pointer', marginBottom: 2 };
const letterRevealStageStyle = { position: 'relative', width: 'min(560px, 100%)', minHeight: 640, marginTop: 12, paddingTop: 12 };
const openedEnvelopeStyle = (accent, image) => ({ position: 'absolute', left: '50%', bottom: 12, width: 'min(520px, 100%)', aspectRatio: '1.5 / 1', transform: 'translateX(-50%)', borderRadius: 8, backgroundImage: `linear-gradient(180deg, rgba(255,250,242,.08), rgba(60,38,18,.08)), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center', boxShadow: '0 18px 36px rgba(30,24,16,.18)', overflow: 'visible' });
const openedEnvelopeBackStyle = (accent, image) => ({ position: 'absolute', left: 18, right: 18, top: 10, height: '43%', clipPath: 'polygon(0 0, 100% 0, 50% 100%)', backgroundImage: `linear-gradient(180deg, rgba(255,250,242,.48), ${accent}1f), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center top', borderRadius: '8px 8px 0 0', filter: 'saturate(.92) brightness(1.03)' });
const openedEnvelopeFlapStyle = (accent, image) => ({ position: 'absolute', left: 0, right: 0, top: 0, height: '58%', transformOrigin: '50% 0', clipPath: 'polygon(0 0, 100% 0, 50% 100%)', backgroundImage: `linear-gradient(180deg, rgba(255,252,244,.24), rgba(72,46,24,.12)), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center top', boxShadow: '0 10px 22px rgba(45,32,18,.12)', animation: 'letterEnvelopeOpen .55s ease-out both' });
const openedEnvelopePocketStyle = (accent, image) => ({ position: 'absolute', left: 0, right: 0, bottom: 0, height: '68%', clipPath: 'polygon(0 0, 50% 56%, 100% 0, 100% 100%, 0 100%)', backgroundImage: `linear-gradient(180deg, rgba(255,248,235,.22), rgba(62,40,22,.1)), url(${image})`, backgroundSize: 'cover', backgroundPosition: 'center bottom', border: `1px solid ${C.mist}55`, borderTop: 0, borderRadius: '0 0 8px 8px', zIndex: 3 });
const openedEnvelopeSealStyle = (accent) => ({ position: 'absolute', left: '50%', bottom: '36%', width: 42, height: 42, transform: 'translateX(-50%)', borderRadius: 999, background: accent, border: '3px solid rgba(255,250,242,.9)', boxShadow: '0 7px 14px rgba(30,24,16,.18)', zIndex: 4 });
const revealedLetterFrameStyle = { position: 'relative', zIndex: 2, width: 'min(420px, 76%)', margin: '0 auto 190px', borderRadius: 6, background: '#f5e4c4', boxShadow: '0 24px 38px rgba(38,27,15,.22)', overflow: 'hidden', animation: 'letterPaperPull .82s cubic-bezier(.2,.72,.15,1) both' };
const revealedLetterImageStyle = { display: 'block', width: '100%', height: 'auto', filter: 'saturate(.98) contrast(1.02)' };
const letterAnimationCss = `
@keyframes letterPaperPull {
  0% { transform: translateY(260px) scale(.82); opacity: .25; }
  55% { transform: translateY(74px) scale(.93); opacity: 1; }
  100% { transform: translateY(0) scale(1); opacity: 1; }
}
@keyframes letterEnvelopeOpen {
  0% { transform: rotateX(0deg); opacity: 1; }
  100% { transform: rotateX(64deg) translateY(-10px); opacity: .86; }
}
`;
