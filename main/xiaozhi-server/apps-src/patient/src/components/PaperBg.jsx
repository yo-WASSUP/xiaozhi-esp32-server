import { C } from '../theme';

export default function PaperBg({ children, style = {} }) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: `linear-gradient(155deg,${C.paper1} 0%,${C.paper2} 100%)`, ...style }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='250' height='250'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.7' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='250' height='250' filter='url(%23n)' opacity='0.035'/%3E%3C/svg%3E")`
      }} />
      {children}
    </div>
  );
}
