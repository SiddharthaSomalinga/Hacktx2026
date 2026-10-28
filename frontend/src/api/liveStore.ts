import { useSyncExternalStore } from 'react'
import { LIVE_FOR_MS } from '../config'
import { initialLive, liveReducer, type LiveInput, type LiveState } from './live'

// One stream per app, so one store. Hooks re-render when it changes, which is when TanStack
// re-reads their refetchInterval, so polling starts and stops with the stream.
let state: LiveState = initialLive
let threshold = 0
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

/** Re-render once more when the data turns LIVE_FOR_MS old: that is when polling must start. */
function scheduleThreshold() {
  window.clearTimeout(threshold)
  const wait = state.lastGood + LIVE_FOR_MS - Date.now()
  if (wait > 0) {
    threshold = window.setTimeout(() => {
      state = { ...state } // a new snapshot, so subscribers re-render
      emit()
    }, wait + 10)
  }
}

export const liveStore = {
  get: (): LiveState => state,
  dispatch(input: LiveInput): void {
    state = liveReducer(state, input, Date.now())
    scheduleThreshold()
    emit()
  },
  subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}

export function useLiveState(): LiveState {
  return useSyncExternalStore(liveStore.subscribe, liveStore.get)
}
