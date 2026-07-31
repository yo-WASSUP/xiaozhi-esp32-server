import { Heartbeat } from '@phosphor-icons/react';
import { moodMeta } from '../utils/emotion';

export default function MoodIcon({ mood, size = 22, weight = 'duotone', decorative = false }) {
  const meta = moodMeta(mood);
  return (
    <Heartbeat
      size={size}
      weight={weight}
      color={meta.color}
      aria-hidden={decorative ? 'true' : undefined}
      aria-label={decorative ? undefined : `情绪：${meta.label}`}
    />
  );
}
