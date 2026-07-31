import {
  ChartLineUp,
  ChatCircleText,
  FilmStrip,
  VideoCamera,
} from '@phosphor-icons/react';
import { C } from '../theme';

const TABS = [
  { id: 'message', Icon: ChatCircleText, label: '消息' },
  { id: 'call', Icon: VideoCamera, label: '通话' },
  { id: 'history', Icon: ChartLineUp, label: '记录' },
  { id: 'video', Icon: FilmStrip, label: '影像' },
];

export default function TabBar({ tab, setTab }) {
  return (
    <nav
      aria-label="主要功能"
      style={{
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        minHeight: 'calc(72px + env(safe-area-inset-bottom))',
        padding: '6px 8px env(safe-area-inset-bottom)',
        background: 'rgba(249,251,250,.96)',
        borderTop: `1px solid ${C.outline}`,
        display: 'flex',
        zIndex: 50,
      }}
    >
      {TABS.map(({ id, Icon, label }) => {
        const active = tab === id;
        return (
          <button
            type="button"
            key={id}
            aria-current={active ? 'page' : undefined}
            aria-label={label}
            onClick={() => setTab(id)}
            style={{
              flex: 1,
              minWidth: 0,
              minHeight: 60,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 3,
              border: 'none',
              borderRadius: 16,
              background: 'transparent',
              color: active ? C.amber : C.inkFaint,
              cursor: 'pointer',
            }}
          >
            <span style={{
              width: 56,
              height: 30,
              borderRadius: 16,
              background: active ? C.primaryContainer : 'transparent',
              display: 'grid',
              placeItems: 'center',
              transition: 'background-color .18s ease',
            }}>
              <Icon size={22} weight={active ? 'fill' : 'regular'} aria-hidden="true" />
            </span>
            <span style={{ fontSize: 11, fontWeight: active ? 650 : 500 }}>{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
