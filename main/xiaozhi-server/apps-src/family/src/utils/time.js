// 把服务端返回的 UTC/本地时间戳格式化为"今天 HH:mm / 昨天 HH:mm / M/D HH:mm"
export function fmtTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts.replace(' ', 'T') + (ts.endsWith('Z') ? '' : 'Z'));
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const pad = (n) => String(n).padStart(2, '0');
    if (sameDay) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch { return ts; }
}

export function fmtCallTime(iso) {
  try {
    const datePart = String(iso || '').slice(0, 10);
    const d = new Date(`${datePart}T00:00:00`);
    if (Number.isNaN(d.getTime())) return String(iso || '');
    const now = new Date();
    if (d.toDateString() === now.toDateString()) return `今天 ${d.getMonth() + 1}月${d.getDate()}日`;
    const y = new Date(now); y.setDate(now.getDate() - 1);
    if (d.toDateString() === y.toDateString()) return `昨天 ${d.getMonth() + 1}月${d.getDate()}日`;
    return `${d.getMonth() + 1}月${d.getDate()}日`;
  } catch { return iso; }
}
