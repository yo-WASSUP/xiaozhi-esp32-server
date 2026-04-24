import { C } from '../theme';
import { SENDER_NAME } from '../constants';
import { moodMeta } from '../utils/emotion';

export default function StatusHeader({ today }) {
  const mood = today && today.dominant_mood;
  const meta = moodMeta(mood);
  const headline = !today ? '正在载入…'
    : !mood || mood === '无数据' ? '今日还没有对话'
    : meta.score >= 70 ? '父亲今天状态不错'
    : meta.score >= 45 ? '父亲今天还算平稳'
    : '父亲今天情绪偏低，多关心一下';
  return (
    <div style={{ padding: '52px 22px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
      <div>
        <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.1em', marginBottom: 4 }}>您好，{SENDER_NAME}</div>
        <div style={{ fontSize: 22, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em' }}>{headline}</div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 28, marginBottom: 2 }}>{mood && mood !== '无数据' ? meta.emoji : '·'}</div>
        <div style={{ fontSize: 12, color: meta.color, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
          {mood && mood !== '无数据' ? `情绪 · ${meta.label}` : '暂无情绪记录'}
        </div>
      </div>
    </div>
  );
}
