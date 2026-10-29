import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { endpoints } from '../../api/endpoints'
import { keys } from '../../api/queries'
import type { InboxItem } from '../../api/types'
import { paths } from '../../app/paths'
import { Button } from '../../ui/Button'
import { clock, useCountdown } from '../../ui/Countdown'
import { ErrorNote } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { SafetyActions } from '../match/Safety'
import styles from './InboxCard.module.css'

/** FR-36: who (first name and major, D43), what, which table, and Accept / Not now / Mute. */
export function InboxCard({ item, fetchedAt }: { item: InboxItem; fetchedAt: number }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const left = useCountdown(item.seconds_left, fetchedAt)
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: keys.inbox }), client.invalidateQueries({ queryKey: keys.me })])
  const accept = useMutation({
    mutationFn: () => endpoints.accept(item.request_id),
    onSuccess: async ({ match_id }) => {
      await refresh()
      navigate(paths.match(match_id))
    },
  })
  const decline = useMutation({ mutationFn: (mute: boolean) => endpoints.decline(item.request_id, mute), onSuccess: refresh })
  const busy = accept.isPending || decline.isPending
  const who = `${item.seeker_first_name}${item.seeker_major ? ` · ${item.seeker_major}` : ''}`
  return (
    <article className={styles.card} aria-label={`Request from ${who}`}>
      <div className={styles.top}>
        <p className={styles.who}>{who}</p>
        <span className={`mono ${styles.left}`} aria-label={`${clock(left)} left to answer`}>
          {clock(left)}
        </span>
      </div>
      <p>
        wants to study <strong>{item.course_label}</strong> with you at {item.table_label}.
      </p>
      {(accept.isError || decline.isError) && <ErrorNote error={accept.error ?? decline.error} />}
      <div className={styles.buttons}>
        <Button variant="primary" disabled={busy} onClick={() => accept.mutate()}>
          Accept
        </Button>
        <Button variant="secondary" disabled={busy} onClick={() => decline.mutate(false)}>
          Not now
        </Button>
        <Button variant="quiet" disabled={busy} onClick={() => decline.mutate(true)}>
          Mute
        </Button>
      </div>
      <p className={`${s.small} ${s.muted}`}>Not now is silent: {item.seeker_first_name} is never told.</p>
      <SafetyActions other={{ request_id: item.request_id }} name={item.seeker_first_name} onDone={() => void refresh()} />
    </article>
  )
}
