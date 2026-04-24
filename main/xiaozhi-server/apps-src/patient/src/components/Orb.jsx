import { C } from '../theme';
import { useWaveCanvas } from '../hooks/useWaveCanvas';

export default function Orb({ state }) {
  const waveRef = useWaveCanvas(state);
  const hue = state === 'speaking' || state === 'listening' ? C.amber : C.mist;
  const rings = state === 'listening' ? [0, 1, 2] : state === 'idle' ? [0, 1] : [];
  return (
    <div style={{ position: 'relative', width: 260, height: 260, flexShrink: 0 }}>
      <div style={{ position: 'absolute', inset: -40, borderRadius: '50%', background: `radial-gradient(circle,${hue}28 0%,transparent 70%)`, filter: 'blur(24px)', transition: 'background 1s' }} />
      {rings.map(i => (
        <div key={i} style={{
          position: 'absolute',
          inset: state === 'listening' ? -(i * 22 + 8) : -(i * 16 + 4),
          borderRadius: '50%',
          border: `1.5px solid ${hue}${state === 'listening' ? ['55', '3a', '22'][i] : '44'}`,
          animation: state === 'listening' ? `ripple 2.2s ease-out ${i * .65}s infinite` : `breathe ${2.8 + i * .6}s ease-in-out ${i * .4}s infinite`
        }} />
      ))}
      {state === 'thinking' && (
        <div style={{ position: 'absolute', inset: -24, borderRadius: '50%', border: '2.5px solid transparent', borderTopColor: `${C.mist}aa`, borderRightColor: `${C.mist}55`, animation: 'spin 1.6s linear infinite' }} />
      )}
      {state === 'speaking' && (
        <canvas ref={waveRef} width={260} height={260}
          style={{ position: 'absolute', inset: 0, width: 260, height: 260, pointerEvents: 'none' }} />
      )}
      <div style={{ position: 'absolute', inset: 28, borderRadius: '50%', background: `radial-gradient(circle at 33% 30%,${hue}ee,${hue}99)`, boxShadow: `0 0 50px ${hue}55,inset 0 0 25px ${hue}22`, transition: 'background 1.2s,box-shadow 1.2s' }}>
        <div style={{ position: 'absolute', inset: '50%', transform: 'translate(-50%,-50%)', width: 54, height: 54, borderRadius: '50%', background: 'radial-gradient(circle at 32% 28%,rgba(255,255,255,.95),rgba(255,255,255,.18))', boxShadow: '0 2px 12px rgba(255,255,255,.3)' }} />
      </div>
      <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: `1px solid ${hue}33` }} />
    </div>
  );
}
