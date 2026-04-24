// 情绪映射（后端枚举 → 中文 / emoji / 正向分数 / 颜色）
export const MOOD_META = {
  happy:     { label: '愉快', emoji: '😊', score: 90, color: '#5a9070' },
  calm:      { label: '平静', emoji: '😌', score: 72, color: '#7a9480' },
  nostalgic: { label: '怀念', emoji: '🌸', score: 62, color: '#d4924a' },
  neutral:   { label: '平常', emoji: '😐', score: 50, color: '#8a7a6a' },
  lonely:    { label: '孤单', emoji: '😔', score: 38, color: '#8fa3b0' },
  anxious:   { label: '焦虑', emoji: '😟', score: 30, color: '#b87340' },
  sad:       { label: '难过', emoji: '😢', score: 25, color: '#6a7a8a' },
  angry:     { label: '生气', emoji: '😠', score: 22, color: '#c0484a' },
};

export const moodMeta = (m) =>
  MOOD_META[m] || { label: m || '无', emoji: '·', score: 0, color: '#8a7a6a' };

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
      date: d, mood: top.mood, label: meta.label, emoji: meta.emoji,
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
      ...(found || { mood: null, label: '无', emoji: '·', score: 0, color: '#8a7a6a', intensity: 0, count: 0 }),
    });
  }
  return out;
}
