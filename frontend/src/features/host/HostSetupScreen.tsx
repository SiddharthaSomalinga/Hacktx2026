import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { endpoints } from '../../api/endpoints'
import { keys, useSeat } from '../../api/queries'
import { useCanvas } from '../../app/focus'
import { paths } from '../../app/paths'
import { ABOUT_ME_MAX, TOPIC_MAX } from '../../config'
import { Button } from '../../ui/Button'
import { usePanelSnap } from '../../ui/Panel'
import { ErrorNote } from '../../ui/Notes'
import s from '../../ui/screen.module.css'

/** FR-23: today's topic and an optional short "about me". Being findable starts here (FR-24). */
export function HostSetupScreen() {
  const { seatId = '' } = useParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const seat = useSeat(seatId)
  usePanelSnap('full')
  useCanvas(
    seat.data
      ? { kind: 'plan', buildingId: seat.data.building_id, floor: seat.data.floor, tableId: seat.data.table_id, selectedSeatId: seatId }
      : { kind: 'campus' },
  )
  const [topic, setTopic] = useState('')
  const [about, setAbout] = useState('')
  const topicId = useId()
  const aboutId = useId()
  const save = useMutation({
    mutationFn: () => endpoints.hostTopic(topic.trim(), about.trim() || undefined),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.me })
      navigate(paths.host(), { replace: true })
    },
  })
  return (
    <form
      className={s.screen}
      onSubmit={(e) => {
        e.preventDefault()
        if (topic.trim()) save.mutate()
      }}
    >
      <header className={s.group}>
        <p className={s.eyebrow}>HOSTING · STEP 2 OF 2</p>
        <h1 className={s.title}>What are you studying?</h1>
        <p className={`${s.small} ${s.muted}`}>People on the same course will be able to ask to join your table.</p>
      </header>
      <div className={s.field}>
        <label htmlFor={topicId} className={s.label}>
          Today's topic
        </label>
        <input
          id={topicId}
          className={s.input}
          value={topic}
          maxLength={TOPIC_MAX}
          required
          placeholder="e.g. orgo 1 exam prep"
          onChange={(e) => setTopic(e.target.value)}
        />
      </div>
      <div className={s.field}>
        <label htmlFor={aboutId} className={s.label}>
          About you (optional)
        </label>
        <textarea id={aboutId} className={s.textarea} value={about} maxLength={ABOUT_ME_MAX} onChange={(e) => setAbout(e.target.value)} />
        <span className={s.count}>
          {about.length}/{ABOUT_ME_MAX}
        </span>
      </div>
      {save.isError && <ErrorNote error={save.error} />}
      <Button variant="primary" type="submit" block disabled={!topic.trim() || save.isPending}>
        Make me findable
      </Button>
    </form>
  )
}
