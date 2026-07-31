import { C } from '../theme';
import { fmtCallTime } from '../utils/time';
import { moodMeta, padDays } from '../utils/emotion';
import { useEmotionData } from '../hooks/useEmotionData';
import Card from '../components/Card';
import SLabel from '../components/SLabel';
import MoodIcon from '../components/MoodIcon';

export default function HistoryScreen({ onUnbind, unbindBusy = false }) {
  const { trend, today, loading } = useEmotionData();
  const weekDays = padDays(trend, 7);
  const dataDays = weekDays.filter(d => d.count > 0);
  const hasTodaySummary = today && today.conversation_count > 0;
  const dominantMood = today && today.dominant_mood && today.dominant_mood !== '无数据'
    ? moodMeta(today.dominant_mood)
    : null;

  return (
    <div className="screen" style={{ padding: 'calc(24px + env(safe-area-inset-top)) 16px 24px' }}>
      <div className="screen-title">陪伴记录</div>
      <div className="screen-subtitle" style={{ marginBottom: 20 }}>查看家人的情绪趋势与最近陪伴摘要</div>

      <Card style={{ padding: '18px', marginBottom: 16 }}>
        <SLabel>最近摘要</SLabel>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '18px 0', fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>加载中…</div>
        ) : hasTodaySummary ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 10 }}>
              <div style={{ fontSize: 15, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 400 }}>{fmtCallTime(today.date)}</div>
              <div style={{ padding: '4px 10px', borderRadius: 999, background: `${C.amber}18`, color: C.amber, fontSize: 12, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
                共 {today.conversation_count} 轮
              </div>
            </div>
            <div style={{ fontSize: 15, color: C.inkMid, fontWeight: 400, lineHeight: 1.75 }}>{today.summary || '暂无摘要内容'}</div>
            {dominantMood && (
              <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: dominantMood.color, fontWeight: 500 }}>
                <MoodIcon mood={today.dominant_mood} size={18} decorative />
                主要情绪：{dominantMood.label}
              </div>
            )}
          </>
        ) : (
          <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, lineHeight: 1.8, textAlign: 'center', padding: '18px 0' }}>
            今天还没有对话记录。家人和小暖完成陪伴后，这里会显示最近摘要。
          </div>
        )}
      </Card>

      <Card style={{ padding: '18px' }}>
        <SLabel>近 7 天情绪</SLabel>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px 0', fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>加载中…</div>
        ) : dataDays.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px 0', fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>最近 7 天还没有情绪记录</div>
        ) : (
          <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', height: 90 }}>
            {weekDays.map((d, i) => {
              const h = Math.round((d.score / 100) * 78);
              const isToday = i === weekDays.length - 1;
              const hasData = d.count > 0;
              return (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0 }}>
                  <div style={{ fontSize: 9, color: hasData ? C.inkFaint : C.mist, fontFamily: 'Noto Sans SC' }}>{hasData ? d.score : '-'}</div>
                  <div
                    title={`${d.dayLabel}，${d.label}，${d.count} 次`}
                    style={{ height: Math.max(h, hasData ? 4 : 2), width: '100%', borderRadius: 6, background: hasData ? (isToday ? C.amber : d.color) : `${C.mist}22`, opacity: hasData ? 1 : 0.35 }}
                  />
                  <div style={{ fontSize: 9, color: isToday ? C.amber : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: isToday ? 400 : 300, whiteSpace: 'nowrap' }}>{d.dayLabel}</div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {onUnbind && (
        <Card style={{ padding: '18px', marginTop: 16 }}>
          <SLabel>设备绑定</SLabel>
          <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, lineHeight: 1.7, marginTop: 8 }}>
            需要重新配对家属端时，可以在这里解除当前绑定。
          </div>
          <button
            onClick={onUnbind}
            disabled={unbindBusy}
            style={unbindButtonStyle(unbindBusy)}
          >
            {unbindBusy ? '解绑中' : '解除绑定'}
          </button>
        </Card>
      )}
    </div>
  );
}

const unbindButtonStyle = (busy) => ({
  width: '100%',
  height: 40,
  marginTop: 12,
  border: `1px solid ${C.red}44`,
  borderRadius: 14,
  background: `${C.red}10`,
  color: C.red,
  fontSize: 13,
  fontFamily: 'Noto Sans SC',
  cursor: busy ? 'not-allowed' : 'pointer',
  opacity: busy ? .55 : 1,
});
