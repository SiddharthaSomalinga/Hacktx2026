import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router'
import { codeOf } from '../../api/errors'
import { endpoints } from '../../api/endpoints'
import { keys, useBuildings, useSearchStatus } from '../../api/queries'
import type { GroupCount, SearchResult, SearchStatus } from '../../api/types'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { useAnnounce } from '../../ui/Announcer'
import { Button } from '../../ui/Button'
import { clock, useCountdown } from '../../ui/Countdown'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, InfoNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { SafetyActions } from '../match/Safety'
import { PushOptIn } from '../push/PushOptIn'
import { collapsePrompt, loadResult, saveResult } from './pending'
import styles from './SearchScreen.module.css'

// Leaving the results without joining cancels the preview (D49), so a later seat link doesn't
// fail with already_searching. Deferred, so React's dev-mode remount doesn't cancel on open.
const pendingCancel = new Map<string, number>()

function useCancelPreviewOnLeave(id: string, preview: boolean) {
  const previewRef = useRef(preview)
  previewRef.current = preview
  useEffect(() => {
    window.clearTimeout(pendingCancel.get(id))
    return () => {
      if (!previewRef.current) return
      pendingCancel.set(id, window.setTimeout(() => void endpoints.cancelSearch(id).catch(() => undefined), 400))
    }
  }, [id])
}

function badges(groups: GroupCount[] | undefined): Record<string, string> {
  const byBuilding: Record<string, number> = {}
  for (const g of groups ?? []) byBuilding[g.building_id] = (byBuilding[g.building_id] ?? 0) + g.count
  return Object.fromEntries(Object.entries(byBuilding).map(([id, n]) => [id, `${n} studying`]))
}

function Groups({ title, groups }: { title: string; groups: GroupCount[] }) {
  const buildings = useBuildings()
  const name = (id: string) => buildings.data?.find((b) => b.id === id)?.name ?? id.toUpperCase()
  return (
    <section className={s.group}>
      <h2 className={s.eyebrow}>{title}</h2>
      <ul className={s.list}>
        {groups.map((g) => (
          <li key={`${g.building_id}-${g.floor}`} className={styles.place}>
            <Users size={18} aria-hidden />
            <span>
              {name(g.building_id)} · Floor {g.floor}
            </span>
            <span className={`mono ${styles.n}`}>{g.count}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Preview({ id, status, stored }: { id: string; status: SearchStatus; stored: SearchResult | null }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const join = useMutation({
    mutationFn: () => endpoints.join(id),
    onSuccess: (st) => client.setQueryData(keys.search(id), st),
  })
  const leave = useMutation({
    mutationFn: () => endpoints.cancelSearch(id),
    onSettled: () => {
      collapsePrompt()
      navigate(paths.home(), { replace: true })
    },
  })
  const offered = stored?.offered_group ?? status.offered_group
  const same = stored?.same_course ?? []
  const related = stored?.related ?? []
  const nobody = stored !== null && same.length === 0 && related.length === 0

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>YOUR TOPIC</p>
        <h1 className={s.title}>{status.label}</h1>
      </header>
      {nobody ? (
        <InfoNote>No one's studying this right now. You can still find a good seat.</InfoNote>
      ) : stored ? (
        <>
          {offered === 'related' && <p className={s.muted}>No one is on this course right now, but these people study the same subject.</p>}
          {offered === 'same_course' && same.length > 0 && <Groups title="SAME COURSE · NAMES STAY HIDDEN" groups={same} />}
          {offered === 'related' && <Groups title="RELATED SUBJECT · NAMES STAY HIDDEN" groups={related} />}
          {!stored.has_real_hosts && <InfoNote>Everyone here is simulated for the demo, so nobody can take a request.</InfoNote>}
        </>
      ) : (
        <p className={s.muted}>You have a search in progress.</p>
      )}
      {join.isError && <ErrorNote error={join.error} />}
      <div className={s.actions}>
        {(stored === null || stored.has_real_hosts) && !nobody && codeOf(join.error) !== 'no_real_hosts' && (
          <Button variant="primary" block disabled={join.isPending} onClick={() => join.mutate()}>
            Ask to join them
          </Button>
        )}
        <Button variant={nobody ? 'primary' : 'quiet'} block disabled={leave.isPending} onClick={() => leave.mutate()}>
          Find a seat instead
        </Button>
      </div>
      <p className={`${s.small} ${s.muted}`}>
        We ask one person at a time. They see your first name and major, and you see theirs. Where they sit stays hidden until they accept.
      </p>
    </div>
  )
}

function Waiting({ id, status }: { id: string; status: SearchStatus }) {
  const navigate = useNavigate()
  const left = useCountdown(status.seconds_left)
  const announce = useAnnounce()
  const asking = status.asking
  const name = asking?.first_name
  useEffect(() => {
    if (name) announce(`Asking ${name}`)
  }, [name, announce])
  const cancel = useMutation({ mutationFn: () => endpoints.cancelSearch(id), onSettled: () => navigate(paths.home(), { replace: true }) })
  const fraction = Math.max(0, Math.min(1, left / 300))
  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>{status.label.toUpperCase()}</p>
        <h1 className={s.title}>{asking ? `Asking ${asking.first_name}${asking.major ? ` · ${asking.major}` : ''}` : 'Finding the next person…'}</h1>
      </header>
      {asking && (
        <div className={styles.timer}>
          <svg viewBox="0 0 48 48" width="64" height="64" aria-hidden>
            <circle cx="24" cy="24" r="20" className={styles.track} />
            <circle cx="24" cy="24" r="20" className={styles.progress} pathLength={1} style={{ strokeDashoffset: 1 - fraction }} />
          </svg>
          <div>
            <p className={`mono ${styles.left}`}>{clock(left)}</p>
            <p className={`${s.small} ${s.muted}`}>left for them to answer. If they can't, we ask the next person.</p>
          </div>
        </div>
      )}
      <PushOptIn prompt="Get a notification when they answer." />
      <div className={s.actions}>
        <Button variant="secondary" block disabled={cancel.isPending} onClick={() => cancel.mutate()}>
          Cancel search
        </Button>
      </div>
      {asking && status.request_id && <SafetyActions other={{ request_id: status.request_id }} name={asking.first_name} />}
    </div>
  )
}

function Ended({ status, stored }: { status: SearchStatus; stored: { result: SearchResult; topic: string } | null }) {
  const navigate = useNavigate()
  const retry = useMutation({
    mutationFn: () => endpoints.search(stored?.topic ?? status.label, true),
    onSuccess: (result) => {
      saveResult(result, stored?.topic ?? status.label)
      navigate(paths.search(result.search_id), { replace: true })
    },
  })
  const exhausted = status.status === 'exhausted'
  const canRelate = exhausted && stored?.result.offered_group === 'same_course' && stored.result.related.length > 0
  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>{status.label.toUpperCase()}</p>
        <h1 className={s.title}>{exhausted ? "No one's free right now" : 'Search cancelled'}</h1>
        {exhausted && <p className={s.muted}>Everyone we asked was busy. Here's a good seat instead.</p>}
      </header>
      {retry.isError && <ErrorNote error={retry.error} />}
      <div className={s.actions}>
        <Button
          variant="primary"
          block
          onClick={() => {
            collapsePrompt()
            navigate(paths.home(), { replace: true })
          }}
        >
          Find a seat
        </Button>
        {canRelate && (
          <Button variant="secondary" block disabled={retry.isPending} onClick={() => retry.mutate()}>
            Try people studying related material
          </Button>
        )}
      </div>
    </div>
  )
}

export function SearchScreen() {
  const { searchId = '' } = useParams()
  const navigate = useNavigate()
  const status = useSearchStatus(searchId)
  const stored = loadResult(searchId)
  const st = status.data
  const preview = st?.status === 'active' && !st.joined
  useCancelPreviewOnLeave(searchId, preview)
  usePanelSnap(preview ? 'half' : 'half')
  useCanvas({ kind: 'campus', badges: preview ? badges(stored?.result.offered_group === 'related' ? stored.result.related : stored?.result.same_course) : {} })

  useEffect(() => {
    if (st?.status === 'matched' && st.match_id) navigate(paths.match(st.match_id), { replace: true })
  }, [st?.status, st?.match_id, navigate])

  if (status.isError && !st) {
    return (
      <div className={s.screen}>
        <ErrorNote error={status.error} onRetry={() => void status.refetch()} />
        <Button variant="secondary" block onClick={() => navigate(paths.home(), { replace: true })}>
          Back to the map
        </Button>
      </div>
    )
  }
  if (!st) return <Loading label="Checking your search…" />
  if (st.status === 'matched') return <Loading label="They said yes. Opening your match…" />
  if (st.status === 'active') return st.joined ? <Waiting id={searchId} status={st} /> : <Preview id={searchId} status={st} stored={stored?.result ?? null} />
  return <Ended status={st} stored={stored} />
}
