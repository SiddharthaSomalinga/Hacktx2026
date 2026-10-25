import type { PublicState } from '../api/types'

// The same shapes as the floor plan's chairs, small: state is never shown by color alone (D45).
export function StateGlyph({ state, size = 16 }: { state: PublicState | 'foryou'; size?: number }) {
  const common = { width: size, height: size, viewBox: '0 0 16 16', 'aria-hidden': true } as const
  switch (state) {
    case 'open':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="12" height="12" rx="3" fill="var(--surface)" stroke="var(--open)" strokeWidth="2" />
        </svg>
      )
    case 'occupied':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="12" height="12" rx="3" fill="var(--occupied-fill)" stroke="var(--occupied)" strokeWidth="2" />
        </svg>
      )
    case 'likely_opening':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="12" height="12" rx="3" fill="var(--likely-fill)" stroke="var(--likely)" strokeWidth="1.6" strokeDasharray="2.6 1.8" />
          <rect x="5.5" y="6.5" width="5" height="4.5" rx="1.2" fill="var(--likely)" />
          <path d="M6.6 6.5v-1a1.4 1.4 0 0 1 2.8 0v1" fill="none" stroke="var(--likely)" strokeWidth="1" />
        </svg>
      )
    case 'offline':
      return (
        <svg {...common}>
          <rect x="2" y="2" width="12" height="12" rx="3" fill="var(--offline-fill)" stroke="var(--offline)" strokeWidth="1.5" />
          <path d="M4 12 12 4M2.5 9.5l7-7M6.5 13.5l7-7" stroke="var(--offline)" strokeWidth="1" />
        </svg>
      )
    case 'foryou':
      return (
        <svg {...common}>
          <rect x="1" y="1" width="14" height="14" rx="4" fill="none" stroke="var(--foryou)" strokeWidth="1.5" />
          <rect x="4" y="4" width="8" height="8" rx="2" fill="var(--foryou)" />
        </svg>
      )
  }
}

export const STATE_WORDS: Record<PublicState, string> = {
  open: 'Open',
  occupied: 'Occupied',
  likely_opening: 'Likely opening',
  offline: 'No signal',
}
