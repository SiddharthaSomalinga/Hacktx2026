import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { endpoints } from '../../api/endpoints'
import { useBuildings } from '../../api/queries'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { useSession } from '../account/session'
import { promptCollapsed } from '../seeker/pending'
import { BuildingList } from './BuildingList'
import { TopicPill, TopicPrompt } from './TopicPrompt'

export function HomeScreen() {
  useCanvas({ kind: 'campus' })
  usePanelSnap('half')
  const navigate = useNavigate()
  const buildings = useBuildings()
  const { me } = useSession()
  const [collapsed, setCollapsed] = useState(promptCollapsed)

  // Returning to the app with something in progress goes straight back to it (/me restore).
  const matchId = me.data?.match_id
  const searchId = me.data?.search_id
  useEffect(() => {
    if (matchId) {
      navigate(paths.match(matchId), { replace: true })
      return
    }
    if (searchId) {
      let live = true
      void endpoints
        .searchStatus(searchId)
        .then((st) => live && st.joined && st.status === 'active' && navigate(paths.search(searchId), { replace: true }))
        .catch(() => undefined)
      return () => {
        live = false
      }
    }
  }, [matchId, searchId, navigate])

  const roleActive = Boolean(me.data?.host || matchId)
  const list = buildings.data ?? []
  const open = list.reduce((n, b) => n + b.open, 0)
  const simulated = list.filter((b) => b.is_simulated).length

  return (
    <div className={s.screen}>
      {!roleActive &&
        (collapsed ? <TopicPill onOpen={() => setCollapsed(false)} /> : <TopicPrompt onSkip={() => setCollapsed(true)} />)}

      <section className={s.group} aria-labelledby="campus-now">
        <h2 id="campus-now" className={s.eyebrow}>
          Campus right now
        </h2>
        {buildings.data ? (
          <>
            <p>
              <span className={s.big}>{open}</span> <span className={s.subtitle}>open seats</span>
            </p>
            <p className={`${s.small} ${s.muted}`}>
              Across {list.length} buildings{simulated > 0 ? ` · ${simulated} simulated for the demo` : ''}. Tap one to see its floors.
            </p>
          </>
        ) : buildings.isError ? (
          <ErrorNote error={buildings.error} onRetry={() => void buildings.refetch()} />
        ) : (
          <Loading label="Reading the seat sensors…" />
        )}
      </section>

      {buildings.isError && buildings.data && <ErrorNote error={buildings.error} />}
      {list.length > 0 && <BuildingList buildings={list} />}
    </div>
  )
}
