import { C } from '../theme';

export default function PaperBg({ children, style = {} }) {
  return (
    <div style={{ width: '100%', height: '100%', background: `linear-gradient(160deg,${C.paper1},${C.paper2})`, position: 'relative', overflow: 'hidden', ...style }}>
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', opacity: .6,
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E")`
      }} />
      {children}
    </div>
  );
}
