import { C } from '../theme';

export default function WaveBars({ state }) {
  const active = state === 'listening' || state === 'speaking';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 3, height: 32 }}>
      {Array.from({ length: 20 }, (_, i) => {
        const h = active ? 8 + Math.abs(Math.sin(i * .8)) * 20 : 3;
        return (
          <div key={i} style={{
            width: 3, borderRadius: 2, transformOrigin: 'bottom',
            height: `${h}px`,
            background: active ? `rgba(212,146,74,${.28 + Math.sin(i * .5) * .15})` : `${C.mist}33`,
            animation: active ? `barDance ${.7 + Math.sin(i) * .3}s ease-in-out ${(i * .07).toFixed(2)}s infinite` : 'none',
            transition: 'height .35s,background .5s',
          }} />
        );
      })}
    </div>
  );
}
