// Storage that never throws: private browsing and blocked storage behave like an empty store.

const memory = new Map<string, string>()

export function safeStorage(kind: 'local' | 'session'): Storage {
  const get = (): Storage | null => {
    try {
      return kind === 'local' ? window.localStorage : window.sessionStorage
    } catch {
      return null
    }
  }
  return {
    get length() {
      return get()?.length ?? memory.size
    },
    clear: () => {
      try {
        get()?.clear()
      } catch {
        memory.clear()
      }
    },
    key: (i: number) => get()?.key(i) ?? null,
    getItem: (k: string) => {
      try {
        return get()?.getItem(k) ?? memory.get(k) ?? null
      } catch {
        return memory.get(k) ?? null
      }
    },
    setItem: (k: string, v: string) => {
      try {
        get()?.setItem(k, v)
      } catch {
        memory.set(k, v)
      }
    },
    removeItem: (k: string) => {
      try {
        get()?.removeItem(k)
      } catch {
        memory.delete(k)
      }
    },
  }
}

export const session = safeStorage('session')
export const local = safeStorage('local')

export function readJson<T>(store: Storage, key: string): T | null {
  const raw = store.getItem(key)
  if (raw === null) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}
