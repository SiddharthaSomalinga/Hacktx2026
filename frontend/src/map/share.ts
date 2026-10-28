import type { BuildingSummary } from '../api/types'

export type Share = 'high' | 'mid' | 'low' | 'none'

/**
 * FR-8 building color by open share. The share is open ÷ seats reporting (D51), so a building is
 * judged by its working sensors; it is grey only when every seat is offline.
 */
export function shareOf(b: Pick<BuildingSummary, 'open' | 'total' | 'offline'>): Share {
  const reporting = b.total - b.offline
  if (reporting <= 0) return 'none'
  const share = b.open / reporting
  if (share >= 0.3) return 'high'
  if (share >= 0.1) return 'mid'
  return 'low'
}

export const SHARE_VAR: Record<Share, string> = {
  high: 'var(--share-high)',
  mid: 'var(--share-mid)',
  low: 'var(--share-low)',
  none: 'var(--share-none)',
}

export const SHARE_WORDS: Record<Share, string> = {
  high: 'plenty open',
  mid: 'filling up',
  low: 'nearly full',
  none: 'no signal',
}

/** Short building code for labels: the id, which is the campus code (PCL, WEL, GDC). */
export const shortName = (id: string) => id.toUpperCase()
