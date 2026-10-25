import { RefreshCw, WifiOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Workbox } from 'workbox-window'
import { useOnline } from '../../lib/clock'
import { Button } from '../../ui/Button'
import styles from './UpdatePrompt.module.css'

/** Registers the service worker (production only), and offers a reload when a new version waits. */
export function UpdatePrompt() {
  const [wb, setWb] = useState<Workbox | null>(null)
  const [waiting, setWaiting] = useState(false)
  const online = useOnline()

  useEffect(() => {
    if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return
    const workbox = new Workbox('/sw.js', { scope: '/' })
    workbox.addEventListener('waiting', () => setWaiting(true))
    workbox.addEventListener('controlling', () => window.location.reload())
    void workbox.register()
    setWb(workbox)
    // A notification tap while the app is open: the service worker asks this tab to navigate.
    const onMessage = (e: MessageEvent) => {
      const data = e.data as { type?: string; url?: string } | null
      if (data?.type === 'navigate' && typeof data.url === 'string' && data.url.startsWith('/')) window.location.assign(data.url)
    }
    navigator.serviceWorker.addEventListener('message', onMessage)
    return () => navigator.serviceWorker.removeEventListener('message', onMessage)
  }, [])

  if (!online) {
    return (
      <div className={styles.toast} role="status">
        <WifiOff size={18} aria-hidden />
        You're offline. Showing the last map we had.
      </div>
    )
  }
  if (!waiting) return null
  return (
    <div className={styles.toast} role="status">
      <RefreshCw size={18} aria-hidden />
      A new version is ready.
      <Button variant="secondary" onClick={() => wb?.messageSkipWaiting()}>
        Reload
      </Button>
    </div>
  )
}
