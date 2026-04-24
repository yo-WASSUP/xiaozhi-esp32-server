import { C } from '../theme';
import Card from '../components/Card';
import SLabel from '../components/SLabel';
import StatusHeader from '../components/StatusHeader';
import { useEmotionData } from '../hooks/useEmotionData';
import { moodMeta, padDays } from '../utils/emotion';

export default function HomeScreen({ setTab }) {
  const { trend, today, loading } = useEmotionData();
  const weekDays = padDays(trend, 7);
  const dataDays = weekDays.filter(d => d.count > 0);
  const avgScore = dataDays.length
    ? Math.round(dataDays.reduce((s, d) => s + d.score, 0) / dataDays.length)
    : null;
  const dist = today && today.mood_distribution;

  return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, overflowY: 'auto', padding: '0 16px 24px', animation: 'fadeUp .4s ease' }}>
      <StatusHeader today={today} />

      {/* mood card */}
      <Card style={{ marginTop: 20, padding: '18px 18px 14px' }}>
        <SLabel>近 7 天情绪</SLabel>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', height: 60, marginBottom: 10 }}>
          {weekDays.map((d, i) => {
            const h = Math.round((d.score / 100) * 52);
            const isToday = i === weekDays.length - 1;
            const hasData = d.count > 0;
            return (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                <div style={{ height: Math.max(h, hasData ? 4 : 2), width: '100%', borderRadius: 4, background: hasData ? (isToday ? C.amber : d.color) : `${C.mist}22`, opacity: hasData ? 1 : 0.4, transition: 'height .4s', boxShadow: isToday && hasData ? `0 2px 8px ${C.amber}44` : 'none' }} />
                <div style={{ fontSize: 9, color: isToday ? C.amber : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: isToday ? 400 : 300 }}>{d.dayLabel}</div>
              </div>
            );
          })}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
            {loading ? '加载中…'
              : avgScore != null ? <>近 {dataDays.length} 天平均 <span style={{ color: C.ink, fontWeight: 400 }}>{avgScore} 分</span></>
              : '暂无情绪记录'}
          </div>
          <button onClick={() => setTab('history')} style={{ fontSize: 12, color: C.mist, fontFamily: 'Noto Sans SC', fontWeight: 300, background: 'none', border: 'none', cursor: 'pointer', letterSpacing: '.06em' }}>查看详情 →</button>
        </div>
      </Card>

      {/* today summary */}
      <Card style={{ marginTop: 12, padding: '18px' }}>
        <SLabel>今日陪伴摘要</SLabel>
        {today && today.conversation_count > 0 ? (
          <>
            <div style={{ fontSize: 15, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, lineHeight: 1.9, letterSpacing: '.03em' }}>
              父亲今天和小暖进行了
              <span style={{ color: C.amber }}> {today.conversation_count} </span>
              轮对话{today.patient_message_count > 0 && <>，其中父亲说了 <span style={{ color: C.amber }}>{today.patient_message_count}</span> 次</>}。
              {today.dominant_mood && today.dominant_mood !== '无数据' && (
                <> 主要情绪是 <span style={{ color: moodMeta(today.dominant_mood).color }}>{moodMeta(today.dominant_mood).label}</span>。</>
              )}
            </div>
            {dist && Object.keys(dist).length > 0 && (
              <div style={{ marginTop: 14, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {Object.entries(dist).sort((a, b) => b[1] - a[1]).map(([m, n]) => {
                  const meta = moodMeta(m);
                  return (
                    <div key={m} style={{ padding: '4px 12px', borderRadius: 12, background: `${meta.color}18`, border: `1px solid ${meta.color}33`, fontSize: 12, color: meta.color, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>
                      {meta.emoji} {meta.label} · {n}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <div style={{ fontSize: 14, color: C.inkFaint, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, lineHeight: 1.8, letterSpacing: '.03em', textAlign: 'center', padding: '12px 0' }}>
            {loading ? '加载中…' : '今天还没有对话记录'}
          </div>
        )}
      </Card>

      {/* quick actions */}
      <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
        <button onClick={() => setTab('message')} style={{ flex: 1, padding: '16px 12px', borderRadius: 18, border: `1px solid ${C.sage}44`, background: `${C.sage}14`, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 26 }}>💌</span>
          <span style={{ fontSize: 13, color: C.sage, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>发消息</span>
        </button>
        <button onClick={() => setTab('call')} style={{ flex: 1, padding: '16px 12px', borderRadius: 18, border: `1px solid ${C.amber}44`, background: `${C.amber}12`, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 26 }}>📹</span>
          <span style={{ fontSize: 13, color: C.amber, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>视频通话</span>
        </button>
      </div>
    </div>
  );
}
