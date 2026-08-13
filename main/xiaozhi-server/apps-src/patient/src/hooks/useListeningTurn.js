import { useEffect, useState } from 'react';

export default function useListeningTurn({
  enabled = true,
  aiState,
  connected,
  recording,
  userSpeaking,
}) {
  const canListen = enabled && aiState === 'idle' && connected && recording;
  const [turnActive, setTurnActive] = useState(false);

  useEffect(() => {
    if (!canListen) {
      setTurnActive(false);
      return;
    }
    if (userSpeaking) setTurnActive(true);
  }, [canListen, userSpeaking]);

  return canListen && turnActive;
}
