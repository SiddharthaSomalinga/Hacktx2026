import { AlertTriangle, Info, Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { messageFor } from '../api/errors'
import { Button } from './Button'
import s from './screen.module.css'
import styles from './Notes.module.css'

export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className={s.error} role="alert">
      <AlertTriangle size={18} aria-hidden />
      <div className={styles.grow}>{messageFor(error)}</div>
      {onRetry && (
        <Button variant="quiet" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function InfoNote({ children }: { children: ReactNode }) {
  return (
    <div className={s.note}>
      <Info size={18} aria-hidden />
      <div className={styles.grow}>{children}</div>
    </div>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <p className={styles.loading} role="status">
      <Loader2 size={18} className={styles.spin} aria-hidden />
      {label}
    </p>
  )
}
