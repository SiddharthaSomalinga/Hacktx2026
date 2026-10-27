import { ArrowRight, Search } from 'lucide-react'
import { useId, useState } from 'react'
import { useNavigate } from 'react-router'
import { paths } from '../../app/paths'
import { TOPIC_MAX } from '../../config'
import { Button } from '../../ui/Button'
import s from '../../ui/screen.module.css'
import { useSession } from '../account/session'
import { collapsePrompt, expandPrompt, peekPendingTopic, savePendingTopic } from '../seeker/pending'
import styles from './TopicPrompt.module.css'

/** FR-17: asked when the map opens. Typing leads straight into the seeker flow; Skip collapses it. */
export function TopicPrompt({ onSkip }: { onSkip: () => void }) {
  const navigate = useNavigate()
  const { user } = useSession()
  const [topic, setTopic] = useState(() => peekPendingTopic() ?? '')
  const id = useId()
  const submit = () => {
    const text = topic.trim()
    if (!text) return
    savePendingTopic(text)
    navigate(user ? paths.find() : paths.login(paths.find()))
  }
  return (
    <form
      className={styles.prompt}
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <label htmlFor={id} className={styles.question}>
        What are you studying today?
      </label>
      <div className={styles.inputRow}>
        <Search size={20} className={styles.icon} aria-hidden />
        <input
          id={id}
          className={styles.input}
          value={topic}
          maxLength={TOPIC_MAX}
          placeholder="orgo exam, CS 314 trees, macro…"
          autoComplete="off"
          enterKeyHint="go"
          onChange={(e) => setTopic(e.target.value)}
        />
        <Button variant="primary" type="submit" disabled={!topic.trim()} aria-label="Find people studying this">
          <ArrowRight size={20} aria-hidden />
        </Button>
      </div>
      <div className={s.row}>
        <span className={`${s.small} ${s.muted}`}>We match you with someone on the same course, then show you their table.</span>
        <Button
          variant="quiet"
          className={styles.skip}
          onClick={() => {
            collapsePrompt()
            onSkip()
          }}
        >
          Skip, just find a seat
        </Button>
      </div>
    </form>
  )
}

export function TopicPill({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      className={styles.pill}
      onClick={() => {
        expandPrompt()
        onOpen()
      }}
    >
      <Search size={18} aria-hidden />
      Studying something? Find a partner
    </button>
  )
}
