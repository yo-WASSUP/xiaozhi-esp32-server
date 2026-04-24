import { useEffect, useState } from 'react';
import { C } from '../theme';
import { DEVICE_ID } from '../constants';
import { fmtCallTime } from '../utils/time';
import { padDays } from '../utils/emotion';
import { useEmotionData } from '../hooks/useEmotionData';
import Card from '../components/Card';
import SLabel from '../components/SLabel';

export default function HistoryScreen() {
  const [days, setDays] = useState(7);
  const [historyRaw, setHistoryRaw] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const { trend, loading } = useEmotionData();

  useEffect(() => {
    fetch(`/api/hospice/summary/history?device_id=${encodeURIComponent(DEVICE_ID)}&limit=30`)
      .then(r => r.json())
      .then(list => setHistoryRaw(Array.isArray(list) ? list : []))
      .catch(e => console.error('摘要历史加载失败', e))
      .finally(() => setHistoryLoading(false));
  }, []);

  const weekDays = padDays(trend, days);
  const dataDays = weekDays.filter(d => d.count > 0);

  return (
    <div style={{ position: 'absolute', top: 0, bottom: 80, left: 0, right: 0, overflow: 'auto', padding: '52px 16px 24px', animation: 'fadeUp .4s ease' }}>
      <div style={{ fontSize: 22, color: C.ink, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, letterSpacing: '.06em', marginBottom: 4 }}>历史记录</div>
      <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, marginBottom: 20 }}>父亲的情绪与对话记录</div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {[[7, '近 7 天'], [14, '近 14 天'], [30, '近 30 天']].map(([n, l]) => (
          <button key={n} onClick={() => setDays(n)} style={{ padding: '8px 16px', borderRadius: 14, border: `1px solid ${days === n ? C.amber + '66' : C.mist + '30'}`, background: days === n ? `${C.amber}18` : 'transparent', cursor: 'pointer', fontSize: 13, color: days === n ? C.amber : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: days === n ? 400 : 300 }}>{l}</button>
        ))}
      </div>

      <Card style={{ padding: '18px', marginBottom: 12 }}>
        <SLabel>情绪走势</SLabel>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px 0', fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>加载中…</div>
        ) : dataDays.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px 0', fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>这段时间还没有情绪记录</div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: days > 14 ? 2 : 6, alignItems: 'flex-end', height: 90, marginBottom: 10 }}>
              {weekDays.map((d, i) => {
                const h = Math.round((d.score / 100) * 78);
                const isToday = i === weekDays.length - 1;
                const hasData = d.count > 0;
                return (
                  <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0 }}>
                    {days <= 14 && <div style={{ fontSize: 9, color: hasData ? C.inkFaint : C.mist, fontFamily: 'Noto Sans SC' }}>{hasData ? d.score : '·'}</div>}
                    <div title={`${d.dayLabel} · ${d.label} (${d.count} 次)`}
                      style={{ height: Math.max(h, hasData ? 4 : 2), width: '100%', borderRadius: 4, background: hasData ? (isToday ? C.amber : d.color) : `${C.mist}22`, opacity: hasData ? 1 : 0.35, boxShadow: isToday && hasData ? `0 2px 8px ${C.amber}44` : 'none' }} />
                    {days <= 14 && <div style={{ fontSize: 9, color: isToday ? C.amber : C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: isToday ? 400 : 300, whiteSpace: 'nowrap' }}>{d.dayLabel}</div>}
                  </div>
                );
              })}
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {dataDays.map((d, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <div style={{ width: 6, height: 6, borderRadius: '50%', background: d.color }} />
                  <span style={{ fontSize: 11, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>{d.dayLabel}·{d.label}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      <SLabel>每日摘要</SLabel>
      {historyLoading ? (
        <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, textAlign: 'center', padding: '20px 0' }}>加载中…</div>
      ) : historyRaw.length === 0 ? (
        <Card style={{ padding: '20px', textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, lineHeight: 1.8 }}>
            每日摘要需要离线任务生成，<br />当前还没有摘要记录。
          </div>
        </Card>
      ) : (
        historyRaw.map((s, i) => (
          <Card key={s.id || i} style={{ padding: '16px', marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ fontSize: 14, color: C.ink, fontFamily: 'Noto Sans SC', fontWeight: 400 }}>{fmtCallTime(s.date)}</div>
              {s.conversation_count != null && (
                <div style={{ fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>共 {s.conversation_count} 轮</div>
              )}
            </div>
            <div style={{ fontSize: 14, color: C.inkMid, fontFamily: 'Noto Serif SC,serif', fontWeight: 300, lineHeight: 1.75, letterSpacing: '.02em' }}>{s.summary || '无'}</div>
            {s.mood_trend && (
              <div style={{ marginTop: 8, fontSize: 12, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300 }}>情绪：{s.mood_trend}</div>
            )}
          </Card>
        ))
      )}
    </div>
  );
}
