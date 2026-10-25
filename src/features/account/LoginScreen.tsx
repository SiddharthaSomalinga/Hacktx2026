import { ChevronRight } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router'
import { useDemoUsers } from '../../api/queries'
import { useCanvas } from '../../app/focus'
import { safeNext } from '../../app/paths'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote, Loading } from '../../ui/Notes'
import s from '../../ui/screen.module.css'
import { peekPendingTopic } from '../seeker/pending'
import { useSession } from './session'
import styles from './LoginScreen.module.css'

/** FR-16: pick a demo student. No passwords. The topic typed before this is kept (FR-18). */
export function LoginScreen() {
  usePanelSnap('full')
  useCanvas({ kind: 'campus' })
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const users = useDemoUsers(true)
  const { login, user } = useSession()
  const pending = peekPendingTopic()

  return (
    <div className={s.screen}>
      <header className={s.group}>
        <p className={s.eyebrow}>DEMO LOGIN</p>
        <h1 className={s.title}>Who are you?</h1>
        <p className={`${s.small} ${s.muted}`}>
          {pending ? `We'll look for people studying “${pending}” next. ` : ''}
          Before anyone accepts, others only see your first name and major.
        </p>
      </header>
      {user && <p className={`${s.small} ${s.muted}`}>You're logged in as {user.first_name}. Pick someone else to switch.</p>}
      {users.isError ? (
        <ErrorNote error={users.error} onRetry={() => void users.refetch()} />
      ) : !users.data ? (
        <Loading label="Loading demo students…" />
      ) : users.data.length === 0 ? (
        <p className={s.muted}>No demo students are set up on this server.</p>
      ) : (
        <ul className={s.list}>
          {users.data.map((u) => (
            <li key={u.id}>
              <button
                type="button"
                className={styles.user}
                disabled={login.isPending}
                onClick={() => login.mutate(u.id, { onSuccess: () => navigate(next, { replace: true }) })}
              >
                <span className={styles.avatar} aria-hidden>
                  {u.first_name.slice(0, 1)}
                </span>
                <span className={styles.who}>
                  <span className={styles.name}>{u.first_name}</span>
                  <span className={`${s.small} ${s.muted}`}>{u.major ?? 'Undeclared'}</span>
                </span>
                <ChevronRight size={18} aria-hidden className={styles.chevron} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {login.isError && <ErrorNote error={login.error} />}
    </div>
  )
}
