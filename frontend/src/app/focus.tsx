import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type SeatMark = { seatId: string; label: string }

/** What the full-screen canvas behind the panel shows. Each route declares it. */
export type Focus =
  | { kind: 'campus'; badges?: Record<string, string> }
  | {
      kind: 'plan'
      buildingId: string
      floor: number | null
      tableId?: string | undefined
      selectedSeatId?: string | undefined
      marks?: SeatMark[]
    }

type FocusValue = { focus: Focus; setFocus: (focus: Focus) => void }

const FocusContext = createContext<FocusValue | null>(null)

export function FocusProvider({ children }: { children: ReactNode }) {
  const [focus, setFocus] = useState<Focus>({ kind: 'campus' })
  const value = useMemo(() => ({ focus, setFocus }), [focus])
  return <FocusContext.Provider value={value}>{children}</FocusContext.Provider>
}

export function useFocusState(): FocusValue {
  const value = useContext(FocusContext)
  if (!value) throw new Error('useFocusState outside FocusProvider')
  return value
}

/** Declare what the canvas should show while this screen is open. */
export function useCanvas(focus: Focus): void {
  const { setFocus } = useFocusState()
  const key = JSON.stringify(focus)
  useEffect(() => {
    setFocus(JSON.parse(key) as Focus)
  }, [key, setFocus])
}
