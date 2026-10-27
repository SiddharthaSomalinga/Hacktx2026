import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

const AnnounceContext = createContext<(text: string) => void>(() => {})

/** One polite live region for changes that matter (a request answered, a seat moved), never polls. */
export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [text, setText] = useState('')
  const announce = useCallback((next: string) => {
    setText('')
    window.setTimeout(() => setText(next), 50)
  }, [])
  return (
    <AnnounceContext.Provider value={announce}>
      {children}
      <div className="visually-hidden" aria-live="polite" role="status">
        {text}
      </div>
    </AnnounceContext.Provider>
  )
}

export const useAnnounce = () => useContext(AnnounceContext)
