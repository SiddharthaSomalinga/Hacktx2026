import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router'
import { endpoints } from '../../api/endpoints'
import { keys, useInbox, useSeat } from '../../api/queries'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { useAnnounce } from '../../ui/Announcer'
import { Button } from '../../ui/Button'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, InfoNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { useSession } from '../account/session'
import { PushOptIn } from '../push/PushOptIn'
import { HIDDEN_COPY } from './hiddenReason'
import { InboxCard } from './InboxCard'
import styles from './HostScreen.module.css'

export function HostScreen() {
  const navigate = useNavigate()
  const client = useQueryClient()
  const { me, user } = useSession()
  const host = me.data?.host ?? null
  const seat = useSeat(host?.seat_id)
  const inbox = useInbox(host !== null)
  const announce = useAnnounce()
  usePanelSnap('half')
  useCanvas(
    seat.data
      ? {
          kind: 'plan',
          buildingId: seat.data.building_id,
          floor: seat.data.floor,
          tableId: seat.data.table_id,
          selectedSeatId: seat.data.id,
          marks: [{ seatId: seat.data.id, label: 'You' }],
        }
      : { kind: 'campus' },
  )

  const refresh = () => client.invalidateQueries({ queryKey: keys.me })
  const mute = useMutation({ mutationFn: (muted: boolean) => endpoints.hostMute(muted), onSuccess: refresh })
  const confirm = useMutation({ mutationFn: endpoints.hostConfirm, onSuccess: refresh })
  const stop = useMutation({
    mutationFn: () => endpoints.hostToggle(false),
    onSuccess: async () => {
      await refresh()
      navigate(paths.home(), { replace: true })
    },
  })

  const count = inbox.data?.length ?? 0
  const previous = useRef(0)
  useEffect(() => {
    if (count > previous.current) announce('New study request')
    previous.current = count
  }, [count, announce])

  if (!user && !me.isPending) return <InfoNote>Log in to host from your seat.</InfoNote>
  if (me.isPending) return <Loading label="Checking your session…" />
  if (!host) {
    return (
      <div className={s.screen}>
        <h1 className={s.title}>You're not hosting</h1>
        <p className={s.muted}>Sit down, then tap your chair on the floor plan or scan the QR code on it.</p>
        <Button variant="primary" block onClick={() => navigate(paths.home())}>
          Find your seat
        </Button>
      </div>
    )
  }

  const findable = host.status === 'findable'
  const reason = host.hidden_reason
  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>
          HOSTING · {seat.data ? `${seat.data.building_id.toUpperCase()} · ${seat.data.table_label.toUpperCase()} · SEAT ${seat.data.position}` : host.seat_id}
        </p>
        <h1 className={s.title}>{host.label ?? 'No topic yet'}</h1>
        <p className={`${styles.status} ${findable ? styles.findable : ''}`}>
          <span className={styles.dot} aria-hidden />
          {findable ? 'Findable by people on your course' : 'Hidden right now'}
        </p>
        {reason && reason !== 'confirm_pending' && <p className={`${s.small} ${s.muted}`}>{HIDDEN_COPY[reason]}</p>}
        {reason === 'needs_topic' && (
          <Link to={paths.hostSetup(host.seat_id)} className={styles.link}>
            Add your topic
          </Link>
        )}
      </header>

      {reason === 'confirm_pending' && (
        <div className={styles.confirm} role="alert">
          <p>{HIDDEN_COPY.confirm_pending}</p>
          {confirm.isError && <ErrorNote error={confirm.error} />}
          <Button variant="primary" block disabled={confirm.isPending} onClick={() => confirm.mutate()}>
            I'm still open to partners
          </Button>
        </div>
      )}

      {me.data?.match_id && (
        <Button variant="primary" block onClick={() => navigate(paths.match(me.data?.match_id ?? ''))}>
          Open your match
        </Button>
      )}

      <section className={s.group} aria-label="Requests">
        <h2 className={s.eyebrow}>REQUESTS</h2>
        {inbox.isError && <ErrorNote error={inbox.error} />}
        {count === 0 ? (
          <p className={`${s.small} ${s.muted}`}>{findable ? 'No requests yet. They appear here, and as a notification if you turn those on.' : 'No requests while you are hidden.'}</p>
        ) : (
          inbox.data?.map((item) => <InboxCard key={item.request_id} item={item} fetchedAt={inbox.dataUpdatedAt} />)
        )}
      </section>

      {findable && <PushOptIn prompt="Get requests on your lock screen." />}

      <div className={s.actions}>
        <Button variant="secondary" block disabled={mute.isPending} onClick={() => mute.mutate(!host.muted)}>
          {host.muted ? 'Unmute requests' : 'Mute new requests'}
        </Button>
        <Button variant="danger" block disabled={stop.isPending} onClick={() => stop.mutate()}>
          Stop hosting
        </Button>
      </div>
      {(mute.isError || stop.isError) && <ErrorNote error={mute.error ?? stop.error} />}
    </div>
  )
}
