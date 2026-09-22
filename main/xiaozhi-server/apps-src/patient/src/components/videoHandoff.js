export function createVideoHandoff(initialState, onCommit) {
  let activeState = initialState;
  let requestId = 0;

  return {
    get activeState() {
      return activeState;
    },

    async request(nextState, prepare) {
      requestId += 1;
      const currentRequestId = requestId;
      if (nextState === activeState) return activeState;
      await prepare(nextState);
      if (currentRequestId !== requestId) return activeState;
      const previousState = activeState;
      activeState = nextState;
      onCommit(nextState, previousState);
      return activeState;
    },

    cancel() {
      requestId += 1;
    },
  };
}


export function getVideoLayers(activeState, requestedState, activeReady = true) {
  const activeLayer = {
    state: activeState,
    role: activeReady ? 'active' : 'preparing',
  };
  if (requestedState === activeState) return [activeLayer];
  return [
    activeLayer,
    { state: requestedState, role: 'preparing' },
  ];
}
