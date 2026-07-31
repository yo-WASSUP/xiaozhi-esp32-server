import { useEffect, useState } from 'react';
import PaperBg from './components/PaperBg';
import TabBar from './components/TabBar';
import MessageScreen from './screens/MessageScreen';
import CallScreen from './screens/CallScreen';
import HistoryScreen from './screens/HistoryScreen';
import LegacyVideoScreen from './screens/LegacyVideoScreen';
import PairingScreen from './screens/PairingScreen';
import { clearPairing, DEVICE_ID, FAMILY_ID, hasPairing } from './constants';

export default function App() {
  const [tab, setTab] = useState('message');
  const [paired, setPaired] = useState(hasPairing());
  const [unbindBusy, setUnbindBusy] = useState(false);

  const resetPairing = () => {
    clearPairing();
    setPaired(false);
  };

  const unbind = async () => {
    if (unbindBusy) return;
    if (!window.confirm('解除绑定后，这个家属端需要重新配对才能继续使用。确定解除吗？')) return;
    setUnbindBusy(true);
    try {
      const params = new URLSearchParams({ device_id: DEVICE_ID, family_id: FAMILY_ID });
      const r = await fetch(`/api/hospice/pairing/bindings?${params.toString()}`, { method: 'DELETE' });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.error || '解除绑定失败');
      resetPairing();
    } catch (e) {
      alert(e.message || '解除绑定失败');
    } finally {
      setUnbindBusy(false);
    }
  };

  useEffect(() => {
    if (!paired || !DEVICE_ID || !FAMILY_ID) return undefined;
    const es = new EventSource(`/api/hospice/message/stream?device_id=${encodeURIComponent(DEVICE_ID)}`);
    es.addEventListener('pairing.revoked', (event) => {
      try {
        const data = JSON.parse(event.data || '{}');
        if (data.family_id === FAMILY_ID) resetPairing();
      } catch (_) { }
    });
    es.onerror = () => { };
    return () => es.close();
  }, [paired]);

  return (
    <div className="app-shell">
      <PaperBg>
        {!paired ? (
          <PairingScreen />
        ) : (
          <>
            {tab === 'message' && <MessageScreen />}
            {tab === 'call'    && <CallScreen />}
            {tab === 'history' && <HistoryScreen onUnbind={unbind} unbindBusy={unbindBusy} />}
            {tab === 'video'   && <LegacyVideoScreen />}
            <TabBar tab={tab} setTab={setTab} />
          </>
        )}
      </PaperBg>
    </div>
  );
}
