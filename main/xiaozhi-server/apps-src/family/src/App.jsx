import { useState } from 'react';
import PaperBg from './components/PaperBg';
import TabBar from './components/TabBar';
import HomeScreen from './screens/HomeScreen';
import MessageScreen from './screens/MessageScreen';
import CallScreen from './screens/CallScreen';
import HistoryScreen from './screens/HistoryScreen';
import LegacyVideoScreen from './screens/LegacyVideoScreen';
import PairingScreen from './screens/PairingScreen';
import { hasPairing } from './constants';

export default function App() {
  const [tab, setTab] = useState('home');

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden' }}>
      <PaperBg>
        {!hasPairing() ? (
          <PairingScreen />
        ) : (
          <>
            {tab === 'home'    && <HomeScreen setTab={setTab} />}
            {tab === 'message' && <MessageScreen />}
            {tab === 'call'    && <CallScreen />}
            {tab === 'history' && <HistoryScreen />}
            {tab === 'video'   && <LegacyVideoScreen />}
            <TabBar tab={tab} setTab={setTab} />
          </>
        )}
      </PaperBg>
    </div>
  );
}
