import { describe, expect, it } from 'vitest'
import { stateSignature } from './queries'
import type { BuildingDetail } from './types'

type State = 'open' | 'occupied' | 'likely_opening' | 'offline'

function detail(states: State[]): BuildingDetail {
  return {
    id: 'pcl',
    name: 'PCL Library',
    is_simulated: false,
    floors: [
      {
        floor: 2,
        tables: [
          {
            id: 'pcl-2-t1',
            label: 'Table 01',
            x: 30,
            y: 22,
            seats: states.map((state, i) => ({ id: `t1-s${i + 1}`, position: i + 1, state })),
          },
        ],
      },
    ],
  }
}

describe('stateSignature', () => {
  it('changes when a seat moves between any two states', () => {
    const states: State[] = ['open', 'occupied', 'likely_opening', 'offline']
    for (const from of states) {
      for (const to of states.filter((s) => s !== from)) {
        expect(stateSignature(detail([from, 'open']))).not.toBe(stateSignature(detail([to, 'open'])))
      }
    }
  })

  it('stays the same when nothing changed', () => {
    expect(stateSignature(detail(['open', 'occupied']))).toBe(stateSignature(detail(['open', 'occupied'])))
  })
})
