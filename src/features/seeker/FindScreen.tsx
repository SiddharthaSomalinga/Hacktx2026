import { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { codeOf } from '../../api/errors'
import { endpoints } from '../../api/endpoints'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { Button } from '../../ui/Button'
import { ErrorNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { clearPendingTopic, peekPendingTopic, saveResult } from './pending'

/** Submits the typed topic (FR-18) and replaces itself with the results, so Back skips it. */
export function FindScreen() {
  useCanvas({ kind: 'campus' })
  const navigate = useNavigate()
  const [topic] = useState(peekPendingTopic)
  const [error, setError] = useState<unknown>(null)
  const started = useRef(false)

  useEffect(() => {
    if (!topic || started.current) return
    started.current = true
    endpoints
      .search(topic)
      .then((result) => {
        saveResult(result, topic)
        clearPendingTopic()
        navigate(paths.search(result.search_id), { replace: true })
      })
      .catch((e: unknown) => {
        if (codeOf(e) === 'not_logged_in') navigate(paths.login(paths.find()), { replace: true })
        else setError(e)
      })
  }, [topic, navigate])

  if (!topic) return <Navigate to={paths.home()} replace />
  if (error) {
    return (
      <div className={s.screen}>
        <ErrorNote error={error} />
        {codeOf(error) === 'already_hosting' ? (
          <Button variant="primary" block onClick={() => navigate(paths.host(), { replace: true })}>
            Go to hosting
          </Button>
        ) : (
          <Button variant="secondary" block onClick={() => navigate(paths.home(), { replace: true })}>
            Back to the map
          </Button>
        )}
      </div>
    )
  }
  return (
    <div className={s.screen}>
      <p className={s.eyebrow}>MATCHING YOUR TOPIC</p>
      <h1 className={s.title}>“{topic}”</h1>
      <Loading label="Working out the course and who's studying it…" />
    </div>
  )
}
