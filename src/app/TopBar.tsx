import { ArrowLeft, Monitor, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { isUnavailable } from '../api/client'
import { freshness, freshnessText } from '../api/freshness'
import { useBuilding, useBuildings } from '../api/queries'
import { useSession } from '../features/account/session'
import { local } from '../lib/storage'
import { useNow, useOnline } from '../lib/clock'
import { Button, IconButton } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { useFocusState } from './focus'
import { parentOf } from './parent'
import { paths } from './paths'
import styles from './TopBar.module.css'

function Wordmark() {
  return (
    <span className={styles.wordmark}>
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden>
        <rect x="3" y="5" width="16" height="13" rx="4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeDasharray="3.2 2.4" />
        <rect x="6" y="1.5" width="10" height="2.4" rx="1.2" fill="currentColor" />
      </svg>
      <span>ghost seats</span>
    </span>
  )
}

function FreshnessPill() {
  const { focus } = useFocusState()
  const campus = useBuildings(focus.kind === 'campus')
  const plan = useBuilding(focus.kind === 'plan' ? focus.buildingId : undefined)
  const query = focus.kind === 'plan' ? plan : campus
  const online = useOnline()
  const now = useNow()
  const state = freshness({
    updatedAt: query.dataUpdatedAt,
    failed: query.isError,
    unavailable: query.isError && isUnavailable(query.error),
    online,
    now,
  })
  const text = freshnessText(state)
  return (
    <span className={`${styles.pill} ${styles[state.kind]}`} role="status">
      <span className={styles.dot} aria-hidden />
      {text.label}
      {text.detail && <span className={styles.detail}>{text.detail}</span>}
    </span>
  )
}

type Theme = 'system' | 'light' | 'dark'

function applyTheme(theme: Theme) {
  if (theme === 'system') {
    delete document.documentElement.dataset.theme
    local.removeItem('gs-theme')
  } else {
    document.documentElement.dataset.theme = theme
    local.setItem('gs-theme', theme)
  }
}

function AccountMenu({ onClose }: { onClose: () => void }) {
  const { user, logout } = useSession()
  const [theme, setTheme] = useState<Theme>(() => (local.getItem('gs-theme') as Theme | null) ?? 'system')
  const choose = (t: Theme) => {
    setTheme(t)
    applyTheme(t)
  }
  const options: { value: Theme; label: string; icon: typeof Sun }[] = [
    { value: 'system', label: 'System', icon: Monitor },
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
  ]
  return (
    <Dialog title={user ? `${user.first_name}${user.major ? ` · ${user.major}` : ''}` : 'Settings'} onClose={onClose}>
      <fieldset className={styles.themes}>
        <legend>Appearance</legend>
        {options.map(({ value, label, icon: Icon }) => (
          <label key={value} className={styles.theme}>
            <input type="radio" name="theme" value={value} checked={theme === value} onChange={() => choose(value)} />
            <Icon size={18} aria-hidden />
            {label}
          </label>
        ))}
      </fieldset>
      {user && (
        <Button
          variant="secondary"
          block
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSettled: onClose })}
        >
          Log out
        </Button>
      )}
    </Dialog>
  )
}

export function TopBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { user } = useSession()
  const [menu, setMenu] = useState(false)
  const atHome = location.pathname === '/'

  const back = () => {
    // Inside the app, Back is the browser's back. Opened from a link or QR code, it goes up a level.
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0
    if (idx > 0) navigate(-1)
    else navigate(parentOf(location.pathname), { replace: true })
  }

  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        {!atHome && (
          <IconButton aria-label="Back" onClick={back}>
            <ArrowLeft size={20} aria-hidden />
          </IconButton>
        )}
        <button type="button" className={styles.home} onClick={() => navigate(paths.home())} aria-label="Ghost Seats, campus map">
          <Wordmark />
        </button>
      </div>
      <div className={styles.right}>
        <FreshnessPill />
        {user ? (
          <IconButton aria-label={`Account: ${user.first_name}`} onClick={() => setMenu(true)}>
            <span className={styles.initial}>{user.first_name.slice(0, 1)}</span>
          </IconButton>
        ) : (
          <>
            <Button variant="secondary" onClick={() => navigate(paths.login(location.pathname))}>
              Log in
            </Button>
            <IconButton aria-label="Settings" className={styles.settings} onClick={() => setMenu(true)}>
              <Sun size={18} aria-hidden />
            </IconButton>
          </>
        )}
      </div>
      {menu && <AccountMenu onClose={() => setMenu(false)} />}
    </header>
  )
}
