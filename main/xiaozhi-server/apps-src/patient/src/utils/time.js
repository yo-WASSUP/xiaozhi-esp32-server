export function fmtTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts.replace(' ', 'T') + (ts.endsWith('Z') ? '' : 'Z'));
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    if (d.toDateString() === now.toDateString()) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch { return ts; }
}
