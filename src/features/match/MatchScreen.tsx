import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { endpoints } from '../../api/endpoints'
import { keys, useBuilding, useMatch } from '../../api/queries'
import type { Match } from '../../api/types'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { useAnnounce } from '../../ui/Announcer'
import { Button } from '../../ui/Button'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, InfoNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { seatAt } from '../building/find'
import { SafetyActions } from './Safety'
import styles from './MatchScreen.module.css'

function Icebreaker({ match }: { match: Match }) {
  const [imageOk, setImageOk] = useState(true)
  return (
    <figure className={styles.card}>
      {imageOk && <img src={match.card_url} alt="" className={styles.image} onError={() => setImageOk(false)} />}
      <figcaption className={styles.caption}>
        <span className={s.eyebrow}>ICEBREAKER</span>
        <p className={styles.icebreaker}>{match.icebreaker}</p>
      </figcaption>
    </figure>
  )
}

const ENDED: Record<string, { title: string; body: string }> = {
  completed: { title: 'You found each other', body: 'Enjoy studying. The seat sensors take it from here.' },
  cancelled: { title: 'This match was cancelled', body: 'Either side can cancel, or the host left their seat for 2 minutes.' },
  expired: { title: 'This match expired', body: 'Nobody marked “I’m here” within 20 minutes.' },
}

export function MatchScreen() {
  const { matchId = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const announce = useAnnounce()
  const match = useMatch(matchId)
  const m = match.data
  const detail = useBuilding(m?.building_id)
  usePanelSnap('half')

  const seatId = m?.alt_seat_id ?? m?.assigned_seat_id ?? undefined
  const isSeeker = m?.role === 'seeker'
  useCanvas(
    m
      ? {
          kind: 'plan',
          buildingId: m.building_id,
          floor: m.floor,
          tableId: m.table_id,
          marks: seatId ? [{ seatId, label: isSeeker ? 'Your seat' : `${m.other_first_name}'s seat` }] : [],
        }
      : { kind: 'campus' },
  )

  const alt = m?.alt_seat_id
  useEffect(() => {
    if (alt) announce('Your seat was taken. There is a new seat for you.')
  }, [alt, announce])

  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: keys.match(matchId) }), client.invalidateQueries({ queryKey: keys.me })])
  const arrived = useMutation({ mutationFn: () => endpoints.arrived(matchId), onSuccess: refresh })
  const cancel = useMutation({ mutationFn: () => endpoints.cancelMatch(matchId), onSuccess: refresh })

  if (match.isError && !m) {
    return (
      <div className={s.screen}>
        <ErrorNote error={match.error} onRetry={() => void match.refetch()} />
        <Button variant="secondary" block onClick={() => navigate(paths.home(), { replace: true })}>
          Back to the map
        </Button>
      </div>
    )
  }
  if (!m) return <Loading label="Opening your match…" />

  const place = seatAt(detail.data, seatId)
  const who = `${m.other_first_name}${m.other_major ? ` · ${m.other_major}` : ''}`
  const ended = ENDED[m.status]

  if (ended) {
    return (
      <div className={s.screen}>
        <header className={s.group}>
          <p className={s.eyebrow}>MATCH WITH {m.other_first_name.toUpperCase()}</p>
          <h1 className={s.title}>{ended.title}</h1>
          <p className={s.muted}>{ended.body}</p>
        </header>
        <Button variant="primary" block onClick={() => navigate(paths.home(), { replace: true })}>
          Back to the map
        </Button>
        <SafetyActions other={{ match_id: matchId }} name={m.other_first_name} />
      </div>
    )
  }

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>{isSeeker ? 'THEY SAID YES' : 'YOU ACCEPTED'}</p>
        <h1 className={s.title}>{who}</h1>
        <p className={styles.where}>
          {m.building} · Floor {m.floor} · {m.table_label}
          {place ? ` · Seat ${place.seat.position}` : ''}
        </p>
      </header>
      {alt && (
        <InfoNote>
          {isSeeker ? 'Your seat was taken.' : `${m.other_first_name}'s seat was taken.`} The new seat is marked on the plan; you both see the change.
        </InfoNote>
      )}
      {!seatId && <InfoNote>No seat is open at the table right now. Head to the table and look for one nearby.</InfoNote>}
      <Icebreaker match={m} />
      {(arrived.isError || cancel.isError) && <ErrorNote error={arrived.error ?? cancel.error} />}
      <div className={s.actions}>
        {isSeeker ? (
          <Button variant="primary" block disabled={arrived.isPending} onClick={() => arrived.mutate()}>
            I'm here
          </Button>
        ) : (
          <p className={`${s.small} ${s.muted}`}>Your seat's light is blinking blue so {m.other_first_name} can find you.</p>
        )}
        <Button variant="quiet" block disabled={cancel.isPending} onClick={() => cancel.mutate()}>
          Cancel match
        </Button>
      </div>
      <SafetyActions other={{ match_id: matchId }} name={m.other_first_name} />
    </div>
  )
}
