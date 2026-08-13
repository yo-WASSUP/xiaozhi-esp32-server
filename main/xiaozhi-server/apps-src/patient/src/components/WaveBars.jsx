import { Mic, Volume2 } from 'lucide-react';

const BAR_PROFILE = [
  0.42, 0.58, 0.76, 0.54, 0.9, 0.68, 1, 0.72, 0.88,
  0.6, 0.82, 0.96, 0.7, 0.86, 0.56, 0.74, 0.62, 0.46,
];

export default function WaveBars({ source = 'input', level = 0, active = false }) {
  const normalizedLevel = active ? Math.max(0, Math.min(1, level)) : 0;
  const isOutput = source === 'output';
  const Icon = isOutput ? Volume2 : Mic;
  const label = isOutput ? '安安正在说话' : active ? '正在听您说话' : '语音未连接';
  const color = isOutput ? '112, 137, 176' : '82, 132, 108';

  return (
    <div className={`wave-meter wave-meter--${source}`}>
      <div className="wave-meter__label">
        <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
        <span>{label}</span>
      </div>
      <div className="wave-meter__bars" aria-hidden="true">
        {BAR_PROFILE.map((weight, index) => {
          const height = 4 + normalizedLevel * 25 * weight;
          return (
            <div
              key={index}
              style={{
                width: 3,
                height: `${height}px`,
                borderRadius: 2,
                background: `rgba(${color}, ${active ? 0.42 + normalizedLevel * 0.48 : 0.16})`,
                transition: 'height 70ms linear, background 120ms ease',
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
