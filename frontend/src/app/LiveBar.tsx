import { ChevronRight } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import { useMatch, useSearchStatus } from '../api/queries'
import { useSession } from '../features/account/session'
import { clock, useCountdown } from '../ui/Countdown'
import { paths } from './paths'
import styles from './LiveBar.module.css'

/**
 * Pinned at the top of the panel while a role is active (FR-50: one at a time), so a search,
 * match or host session is one tap away from any screen.
 */
export function LiveBar() {
  const { me } = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  const data = me.data
  const matchId = data?.match_id ?? undefined
  const searchId = data?.search_id ?? undefined
  const match = useMatch(matchId, matchId !== undefined && !location.pathname.startsWith('/match/'))
  const search = useSearchStatus(searchId, searchId !== undefined && matchId === undefined && !location.pathname.startsWith('/search/'))
  const left = useCountdown(search.data?.seconds_left)

  if (!data?.user) return null

  if (matchId && !location.pathname.startsWith('/match/')) {
    const m = match.data
    return (
      <Bar tone="foryou" onClick={() => navigate(paths.match(matchId))}>
        {m ? `Matched with ${m.other_first_name} · ${m.table_label}` : 'You have a match'}
      </Bar>
    )
  }
  if (searchId && search.data?.joined && search.data.status === 'active' && !location.pathname.startsWith('/search/')) {
    const asking = search.data.asking
    return (
      <Bar tone="neutral" onClick={() => navigate(paths.search(searchId))}>
        {asking ? `Asking ${asking.first_name} · ${clock(left)} left` : 'Finding a study partner…'}
      </Bar>
    )
  }
  if (data.host && location.pathname !== '/host') {
    const findable = data.host.status === 'findable'
    return (
      <Bar tone={findable ? 'open' : 'neutral'} onClick={() => navigate(paths.host())}>
        {findable ? `Hosting · ${data.host.label ?? 'findable'}` : 'Hosting · hidden right now'}
      </Bar>
    )
  }
  return null
}

function Bar({ tone, onClick, children }: { tone: 'foryou' | 'open' | 'neutral'; onClick: () => void; children: string }) {
  return (
    <button type="button" className={`${styles.bar} ${styles[tone]}`} onClick={onClick}>
      <span className={styles.dot} aria-hidden />
      <span className={styles.text}>{children}</span>
      <ChevronRight size={18} aria-hidden />
    </button>
  )
}
