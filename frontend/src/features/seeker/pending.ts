import { readJson, session } from '../../lib/storage'
import type { SearchResult } from '../../api/types'

// A topic typed before login is kept and submitted after it (FR-18).
const TOPIC = 'gs-pending-topic'
const PROMPT = 'gs-prompt-collapsed'

export const savePendingTopic = (topic: string) => session.setItem(TOPIC, topic)
export const peekPendingTopic = () => session.getItem(TOPIC)
export const clearPendingTopic = () => session.removeItem(TOPIC)

export const promptCollapsed = () => session.getItem(PROMPT) !== null
export const collapsePrompt = () => session.setItem(PROMPT, '1')
export const expandPrompt = () => session.removeItem(PROMPT)

// Search results are only returned by POST /search; keep them (and the words typed, for the
// FR-54 related retry) for the preview screen and reloads.
export type StoredSearch = { result: SearchResult; topic: string }
export const saveResult = (result: SearchResult, topic: string) =>
  session.setItem(`gs-search:${result.search_id}`, JSON.stringify({ result, topic }))
export const loadResult = (id: string) => readJson<StoredSearch>(session, `gs-search:${id}`)
