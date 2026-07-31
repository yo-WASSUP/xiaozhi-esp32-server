import { C } from '../theme';

export default function PaperBg({ children, style = {} }) {
  return (
    <div style={{ width: '100%', height: '100%', background: `linear-gradient(180deg,${C.paper1} 0%,${C.paper2} 100%)`, position: 'relative', overflow: 'hidden', ...style }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: `radial-gradient(circle at 90% 0%, ${C.primaryContainer} 0, transparent 34%)`,
      }} />
      {children}
    </div>
  );
}
