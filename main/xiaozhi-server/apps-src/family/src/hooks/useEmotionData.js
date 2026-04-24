import { useEffect, useState } from 'react';
import { DEVICE_ID } from '../constants';
import { aggregateTrend } from '../utils/emotion';

/**
 * 一次性拉 trend + today_summary，每 60 秒自动刷新
 * @returns {{ trend: Array, today: object|null, loading: boolean, reload: () => void }}
 */
export function useEmotionData() {
  const [trend, setTrend] = useState([]);
  const [today, setToday] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const [tRaw, tToday] = await Promise.all([
        fetch(`/api/hospice/emotion/trend?device_id=${encodeURIComponent(DEVICE_ID)}&days=7`).then(r => r.json()),
        fetch(`/api/hospice/summary/today?device_id=${encodeURIComponent(DEVICE_ID)}`).then(r => r.json()),
      ]);
      setTrend(aggregateTrend(tRaw));
      setToday(tToday);
    } catch (e) {
      console.error('情绪数据加载失败', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);

  return { trend, today, loading, reload: load };
}
