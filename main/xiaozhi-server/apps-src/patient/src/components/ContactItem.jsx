import { C } from '../theme';
import { fmtTime } from '../utils/time';

/** 收件箱左侧的联系人卡片 */
export default function ContactItem({ c, active, onClick }) {
  const preview = c.last_type === 'voice' ? '🎤 语音消息'
    : c.last_type === 'photo' ? '📷 照片'
    : c.last_type === 'video' ? '🎬 视频'
    : (c.last_content || '');
  const meIsLast = c.last_sender_role === 'patient';

  return (
    <div onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '14px 20px', cursor: 'pointer',
      background: active ? `${C.amber}18` : 'transparent',
      borderLeft: active ? `3px solid ${C.amber}` : '3px solid transparent',
      transition: 'background .15s', position: 'relative',
    }}>
      <div style={{ width: 52, height: 52, borderRadius: '50%', background: `${C.amber}22`, border: `1.5px solid ${C.amber}55`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26, flexShrink: 0 }}>
        👤
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
          <div style={{ fontSize: 18, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 400, letterSpacing: '.04em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {c.contact_name}
          </div>
          <div style={{ fontSize: 11, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, flexShrink: 0, marginLeft: 8 }}>
            {fmtTime(c.last_time)}
          </div>
        </div>
        <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {meIsLast ? <span style={{ color: C.sage }}>我: </span> : null}{preview}
        </div>
      </div>
      {c.unread > 0 && (
        <div style={{ position: 'absolute', top: 18, right: 16, minWidth: 20, height: 20, padding: '0 6px', borderRadius: 10, background: C.amber, color: 'white', fontSize: 11, fontFamily: 'Noto Sans SC', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {c.unread}
        </div>
      )}
    </div>
  );
}
