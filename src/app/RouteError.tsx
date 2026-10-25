import { useNavigate, useRouteError } from 'react-router'
import { useCanvas } from './focus'
import { paths } from './paths'
import { Button } from '../ui/Button'
import s from '../ui/screen.module.css'

export function NotFound() {
  useCanvas({ kind: 'campus' })
  const navigate = useNavigate()
  return (
    <div className={s.screen}>
      <h1 className={s.title}>This page doesn't exist</h1>
      <p className={s.muted}>The link may be old. The map is one tap away.</p>
      <Button variant="primary" block onClick={() => navigate(paths.home(), { replace: true })}>
        Open the map
      </Button>
    </div>
  )
}

/** Last resort for a crash in a screen: say so plainly and offer a way back. */
export function RouteError() {
  const error = useRouteError()
  console.error(error)
  return (
    <main style={{ padding: 'var(--s-6) var(--s-4)', maxWidth: '40ch' }}>
      <h1>Something broke</h1>
      <p className={s.muted}>Synapse hit an unexpected error. Reloading usually fixes it.</p>
      <p style={{ marginTop: 'var(--s-4)' }}>
        <Button variant="primary" onClick={() => window.location.assign('/')}>
          Reload Synapse
        </Button>
      </p>
    </main>
  )
}
