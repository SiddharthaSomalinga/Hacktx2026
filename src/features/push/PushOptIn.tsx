import { Bell, BellRing, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../../ui/Button'
import { enablePush, pushEnabled, pushSupport } from './subscription'
import styles from './PushOptIn.module.css'

/** Offered where a notification is actually useful (D50), and asked only on a tap. */
export function PushOptIn({ prompt }: { prompt: string }) {
  const [state, setState] = useState<'idle' | 'on' | 'denied' | 'working' | 'unavailable'>('idle')
  const support = pushSupport()

  useEffect(() => {
    void pushEnabled().then((on) => on && setState('on'))
  }, [])

  if (support === 'unsupported') return null
  if (support === 'needs-install') {
    return (
      <p className={styles.row}>
        <Smartphone size={20} aria-hidden />
        <span>To get notifications on iPhone, tap Share, then “Add to Home Screen”, and open Ghost Seats from there.</span>
      </p>
    )
  }
  if (state === 'on') {
    return (
      <p className={styles.row}>
        <BellRing size={20} aria-hidden />
        <span>Notifications are on for this device.</span>
      </p>
    )
  }
  return (
    <div className={styles.row}>
      <Bell size={20} aria-hidden />
      <span>{state === 'denied' ? 'Notifications are blocked. Allow them in your browser settings.' : state === 'unavailable' ? "Notifications aren't available here." : prompt}</span>
      {state !== 'denied' && state !== 'unavailable' && (
        <Button
          variant="secondary"
          disabled={state === 'working'}
          onClick={() => {
            setState('working')
            void enablePush()
              .then((r) => setState(r === 'granted' ? 'on' : r))
              .catch(() => setState('unavailable'))
          }}
        >
          Turn on
        </Button>
      )}
    </div>
  )
}
