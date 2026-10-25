// Pure helpers for the service worker, kept apart so they can be reasoned about (and tested) alone.

export type Shown = { title: string; body: string; url: string }

const FALLBACK: Shown = { title: 'Synapse', body: 'Something changed. Open Synapse to see it.', url: '/' }

// The only places a notification may open: the push payload URLs in domain/notifications.py.
const ALLOWED = /^\/(host|match\/[\w-]{1,64}|search\/[\w-]{1,64})$/

export function clickTarget(url: unknown): string {
  return typeof url === 'string' && ALLOWED.test(url) ? url : '/'
}

/** Payload `{title, body, url}`; anything malformed still shows a generic notification. */
export function parsePayload(text: string | null | undefined): Shown {
  if (!text) return FALLBACK
  try {
    const data = JSON.parse(text) as Record<string, unknown>
    const str = (v: unknown, max: number) => (typeof v === 'string' && v.trim() ? v.slice(0, max) : null)
    return {
      title: str(data.title, 80) ?? FALLBACK.title,
      body: str(data.body, 240) ?? FALLBACK.body,
      url: clickTarget(data.url),
    }
  } catch {
    return FALLBACK
  }
}
