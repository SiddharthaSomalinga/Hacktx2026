import { useMutation } from '@tanstack/react-query'
import { Flag, ShieldOff } from 'lucide-react'
import { useId, useState } from 'react'
import { endpoints, type Other } from '../../api/endpoints'
import { REPORT_MAX } from '../../config'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import { ErrorNote } from '../../ui/Notes'
import s from '../../ui/screen.module.css'

/**
 * FR-45: block and report from every request and match view. The request or match on screen
 * names the other person (D53); a report also blocks. Both apply in both directions.
 */
export function SafetyActions({ other, name, onDone }: { other: Other; name: string; onDone?: () => void }) {
  const [open, setOpen] = useState<'block' | 'report' | null>(null)
  const [reason, setReason] = useState('')
  const [done, setDone] = useState<string | null>(null)
  const id = useId()
  const block = useMutation({ mutationFn: () => endpoints.block(other) })
  const report = useMutation({ mutationFn: () => endpoints.report(other, reason.trim()) })
  const close = () => setOpen(null)
  const finish = (text: string) => {
    setDone(text)
    close()
    onDone?.()
  }

  if (done) return <p className={`${s.small} ${s.muted}`}>{done}</p>
  return (
    <div className={s.row}>
      <Button variant="quiet" onClick={() => setOpen('block')}>
        <ShieldOff size={16} aria-hidden /> Block
      </Button>
      <Button variant="quiet" onClick={() => setOpen('report')}>
        <Flag size={16} aria-hidden /> Report
      </Button>
      {open === 'block' && (
        <Dialog title={`Block ${name}?`} onClose={close}>
          <div className={s.screen}>
            <p className={s.muted}>You won't be matched with each other again. They aren't told.</p>
            {block.isError && <ErrorNote error={block.error} />}
            <div className={s.actions}>
              <Button variant="primary" block disabled={block.isPending} onClick={() => block.mutate(undefined, { onSuccess: () => finish(`You blocked ${name}.`) })}>
                Block {name}
              </Button>
              <Button variant="quiet" block onClick={close}>
                Cancel
              </Button>
            </div>
          </div>
        </Dialog>
      )}
      {open === 'report' && (
        <Dialog title={`Report ${name}`} onClose={close}>
          <form
            className={s.screen}
            onSubmit={(e) => {
              e.preventDefault()
              if (reason.trim()) report.mutate(undefined, { onSuccess: () => finish(`Thanks. You reported and blocked ${name}.`) })
            }}
          >
            <div className={s.field}>
              <label htmlFor={id} className={s.label}>
                What happened?
              </label>
              <textarea id={id} className={s.textarea} maxLength={REPORT_MAX} value={reason} onChange={(e) => setReason(e.target.value)} required />
              <span className={s.count}>
                {reason.length}/{REPORT_MAX}
              </span>
            </div>
            <p className={`${s.small} ${s.muted}`}>Reporting also blocks them.</p>
            {report.isError && <ErrorNote error={report.error} />}
            <Button variant="primary" type="submit" block disabled={!reason.trim() || report.isPending}>
              Send report
            </Button>
          </form>
        </Dialog>
      )}
    </div>
  )
}
