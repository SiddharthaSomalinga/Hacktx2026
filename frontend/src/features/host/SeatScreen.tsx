import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router'
import { codeOf } from '../../api/errors'
import { endpoints } from '../../api/endpoints'
import { keys, useSeat } from '../../api/queries'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { Button } from '../../ui/Button'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, InfoNote, Loading } from '../../ui/Notes'
import { StateGlyph, STATE_WORDS } from '../../ui/StateGlyph'
import s from '../../ui/screen.module.css'
import { useSession } from '../account/session'
import styles from './SeatScreen.module.css'

/**
 * One sheet for a tapped chair and for its QR code (D49). "Open to study partners" is off by
 * default (FR-20); turning it on links this seat (FR-21), then asks for a topic (D17).
 */
export function SeatScreen() {
  const { seatId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const client = useQueryClient()
  const seat = useSeat(seatId)
  const { user, me } = useSession()
  usePanelSnap('half')
  const at = seat.data
  useCanvas(
    at
      ? { kind: 'plan', buildingId: at.building_id, floor: at.floor, tableId: at.table_id, selectedSeatId: seatId }
      : { kind: 'campus' },
  )

  const link = useMutation({
    mutationFn: () => endpoints.link(seatId),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.me })
      navigate(paths.hostSetup(seatId))
    },
  })
  const cancelSearch = useMutation({
    mutationFn: async () => {
      const id = me.data?.search_id
      if (id) await endpoints.cancelSearch(id)
      await client.invalidateQueries({ queryKey: keys.me })
    },
    onSuccess: () => link.mutate(),
  })

  if (seat.isError && !at) return <ErrorNote error={seat.error} onRetry={() => void seat.refetch()} />
  if (!at) return <Loading label="Finding this seat…" />

  const host = me.data?.host
  const hostingHere = host?.seat_id === seatId
  const code = codeOf(link.error)

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>
          {at.building_id.toUpperCase()} · FLOOR {at.floor}
        </p>
        <h1 className={s.title}>
          {at.table_label} · Seat {at.position}
        </h1>
        <p className={styles.state}>
          <StateGlyph state={at.state} size={20} />
          {STATE_WORDS[at.state]}
        </p>
      </header>

      {hostingHere ? (
        <>
          <InfoNote>You're hosting from this seat.</InfoNote>
          <Button variant="primary" block onClick={() => navigate(paths.host())}>
            Open your host panel
          </Button>
        </>
      ) : host ? (
        <InfoNote>You're already hosting from another seat. Stop hosting there to move.</InfoNote>
      ) : (
        <section className={styles.toggleRow}>
          <div>
            <p className={styles.toggleTitle}>Open to study partners</p>
            <p className={`${s.small} ${s.muted}`}>Sitting here? Let people studying the same course join your table.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={link.isPending || link.isSuccess}
            aria-label="Open to study partners"
            className={styles.switch}
            disabled={link.isPending || cancelSearch.isPending}
            onClick={() => {
              if (!user) navigate(paths.login(location.pathname))
              else link.mutate()
            }}
          >
            <span className={styles.knob} />
          </button>
        </section>
      )}

      {link.isError && (
        <>
          <ErrorNote error={link.error} onRetry={code === 'seat_not_occupied' ? () => link.mutate() : undefined} />
          {code === 'already_searching' && me.data?.search_id && (
            <Button variant="secondary" block disabled={cancelSearch.isPending} onClick={() => cancelSearch.mutate()}>
              Cancel my search and host here
            </Button>
          )}
          {code === 'already_hosting' && (
            <Button variant="secondary" block onClick={() => navigate(paths.host())}>
              Go to hosting
            </Button>
          )}
        </>
      )}
      {!user && !host && <p className={`${s.small} ${s.muted}`}>You'll pick who you are first.</p>}
    </div>
  )
}
