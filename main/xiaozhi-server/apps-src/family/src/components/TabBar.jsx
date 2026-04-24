import { C } from '../theme';

const TABS = [
  { id: 'home', icon: '🏠', label: '主页' },
  { id: 'message', icon: '💌', label: '发消息' },
  { id: 'call', icon: '📹', label: '通话' },
  { id: 'history', icon: '📊', label: '记录' },
];

export default function TabBar({ tab, setTab }) {
  return (
    <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 80, background: C.card, backdropFilter: 'blur(20px)', borderTop: `0.5px solid rgba(143,163,176,.22)`, display: 'flex', zIndex: 50 }}>
      {TABS.map(t => (
        <button key={t.id} onClick={() => setTab(t.id)} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, border: 'none', background: 'transparent', cursor: 'pointer', paddingBottom: 8, position: 'relative' }}>
          <span style={{ fontSize: 24, filter: tab === t.id ? 'none' : 'grayscale(1)', opacity: tab === t.id ? 1 : .45, transition: 'all .2s' }}>{t.icon}</span>
          <span style={{ fontSize: 11, fontFamily: 'Noto Sans SC', fontWeight: 300, color: tab === t.id ? C.amber : C.inkFaint, transition: 'color .2s', letterSpacing: '.04em' }}>{t.label}</span>
          {tab === t.id && <div style={{ position: 'absolute', bottom: 72, width: 24, height: 2.5, borderRadius: 2, background: C.amber }} />}
        </button>
      ))}
    </div>
  );
}
