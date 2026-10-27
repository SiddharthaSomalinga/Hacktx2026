import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'
import type { BuildingSummary } from '../../api/types'
import { paths } from '../../app/paths'
import { SHARE_VAR, SHARE_WORDS, shareOf } from '../../map/share'
import s from '../../ui/screen.module.css'
import styles from './BuildingList.module.css'

/** Every building with its counts (FR-8), most open seats first. Simulated ones say so (FR-13). */
export function BuildingList({ buildings }: { buildings: BuildingSummary[] }) {
  const sorted = [...buildings].sort((a, b) => b.open - a.open)
  return (
    <ul className={s.list} aria-label="Buildings">
      {sorted.map((b) => {
        const share = shareOf(b)
        const parts = [
          { key: 'open', n: b.open },
          { key: 'likely', n: b.likely_opening },
          { key: 'occupied', n: b.occupied },
          { key: 'offline', n: b.offline },
        ]
        return (
          <li key={b.id}>
            <Link to={paths.building(b.id)} className={styles.row} style={{ ['--share' as string]: SHARE_VAR[share] }}>
              <span className={styles.swatch} aria-hidden />
              <span className={styles.main}>
                <span className={styles.name}>
                  {b.name}
                  {b.is_simulated && <span className={s.tag}>SIMULATED</span>}
                </span>
                <span className={styles.bar} aria-hidden>
                  {parts.map((p) => (
                    <span key={p.key} className={styles[p.key]} style={{ flexGrow: p.n }} />
                  ))}
                </span>
                <span className={`${s.small} ${s.muted}`}>
                  {SHARE_WORDS[share]} · {b.likely_opening} likely opening · {b.occupied} taken
                  {b.offline > 0 ? ` · ${b.offline} no signal` : ''}
                </span>
              </span>
              <span className={styles.count}>
                <span className={styles.number}>{b.open}</span>
                <span className={`${s.small} ${s.muted}`}>open</span>
              </span>
              <ChevronRight size={18} className={styles.chevron} aria-hidden />
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
