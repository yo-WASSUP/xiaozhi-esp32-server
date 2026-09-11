export default function useListeningTurn({
  enabled = true,
  aiState,
  connected,
  recording,
  userSpeaking,
}) {
  return enabled && aiState !== 'speaking' && connected && recording && userSpeaking;
}
