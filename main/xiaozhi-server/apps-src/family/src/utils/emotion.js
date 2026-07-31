// 情绪映射（后端枚举 → 中文 / 正向分数 / 颜色）
export const MOOD_META = {
  happy:     { label: '愉快', score: 90, color: '#2f6b55' },
  calm:      { label: '平静', score: 72, color: '#527565' },
  nostalgic: { label: '怀念', score: 62, color: '#7a6f55' },
  neutral:   { label: '平常', score: 50, color: '#6d7b73' },
  lonely:    { label: '孤单', score: 38, color: '#657781' },
  anxious:   { label: '焦虑', score: 30, color: '#896539' },
  sad:       { label: '难过', score: 25, color: '#5d6f7d' },
  angry:     { label: '生气', score: 22, color: '#b3261e' },
};

export const moodMeta = (m) =>
  MOOD_META[m] || { label: m || '无', score: 0, color: '#6d7b73' };

// 把后端"日+情绪"分组聚合成"每日主导情绪"
export function aggregateTrend(rows) {
  const byDate = {};
  for (const r of (rows || [])) {
    const d = r.date;
    if (!byDate[d]) byDate[d] = [];
    byDate[d].push({ mood: r.emotion_mood, intensity: r.avg_intensity, count: r.count });
  }
  return Object.keys(byDate).map(d => {
    const arr = byDate[d].slice().sort((a, b) => b.count - a.count);
    const top = arr[0];
    const meta = moodMeta(top.mood);
    return {
      date: d, mood: top.mood, label: meta.label,
      score: meta.score, color: meta.color, intensity: top.intensity,
      count: byDate[d].reduce((s, x) => s + x.count, 0),
    };
  });
}

// 补齐近 N 天日历，无数据的日子占位
export function padDays(trend, days) {
  const out = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    const found = trend.find(t => t.date === iso);
    out.push({
      date: iso,
      dayLabel: i === 0 ? '今天' : i === 1 ? '昨天' : `${d.getMonth() + 1}/${d.getDate()}`,
      weekLabel: ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()],
      ...(found || { mood: null, label: '无', score: 0, color: '#6d7b73', intensity: 0, count: 0 }),
    });
  }
  return out;
}
