import { C } from '../theme';
import { SENDER_NAME } from '../constants';
import { moodMeta } from '../utils/emotion';
import MoodIcon from './MoodIcon';

export default function StatusHeader({ today }) {
  const mood = today && today.dominant_mood;
  const meta = moodMeta(mood);
  const headline = !today ? '正在载入…'
    : !mood || mood === '无数据' ? '今日还没有对话'
    : meta.score >= 70 ? '家人今天状态不错'
    : meta.score >= 45 ? '家人今天还算平稳'
    : '家人今天情绪偏低，多关心一下';
  return (
    <div style={{ padding: 'calc(24px + env(safe-area-inset-top)) 20px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
      <div>
        <div style={{ fontSize: 13, color: C.inkFaint, fontWeight: 500, marginBottom: 5 }}>您好，{SENDER_NAME}</div>
        <div style={{ fontSize: 24, color: C.ink, fontWeight: 650, letterSpacing: '-.02em', lineHeight: 1.3 }}>{headline}</div>
      </div>
      <div style={{ minWidth: 78, padding: '10px 12px', borderRadius: 16, background: C.card, border: `1px solid ${C.outline}`, display: 'grid', justifyItems: 'center', gap: 4 }}>
        {mood && mood !== '无数据' ? <MoodIcon mood={mood} size={24} decorative /> : null}
        <div style={{ fontSize: 12, color: meta.color, fontWeight: 500, whiteSpace: 'nowrap' }}>
          {mood && mood !== '无数据' ? meta.label : '暂无记录'}
        </div>
      </div>
    </div>
  );
}
