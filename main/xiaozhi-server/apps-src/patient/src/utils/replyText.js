export function getReplyDensity(text) {
  const length = Array.from(String(text || '').trim()).length;
  if (length > 280) return 'very-long';
  if (length > 160) return 'long';
  if (length > 80) return 'medium';
  return 'short';
}
