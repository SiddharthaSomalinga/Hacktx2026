// One way to call the API (ARCH §12): same origin, cookies, typed errors, ETag revalidation.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterMs?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Errors that mean "the backend can't be reached right now", not "you did something wrong". */
export function isUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === 'network' || error.code === 'database_unavailable' || error.code === 'bad_response' || error.status >= 502)
  )
}

const etags = new Map<string, { etag: string; data: unknown }>()

function retryAfter(response: Response): number | undefined {
  const seconds = Number(response.headers.get('Retry-After'))
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : undefined
}

async function errorFrom(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null)
  if (body && typeof body === 'object' && 'error' in body && 'message' in body) {
    const { error, message } = body as { error: unknown; message: unknown }
    return new ApiError(response.status, String(error), String(message), retryAfter(response))
  }
  // A proxy's HTML error page, or anything else that isn't our error body.
  return new ApiError(response.status, 'bad_response', 'The server sent an unexpected response', retryAfter(response))
}

type Method = 'GET' | 'POST' | 'DELETE'

export async function api<T>(method: Method, path: string, body?: unknown, { revalidate = false } = {}): Promise<T> {
  const url = `/api${path}`
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const cached = revalidate ? etags.get(url) : undefined
  if (cached) headers['If-None-Match'] = cached.etag

  let response: Response
  try {
    // no-store: the browser cache would otherwise answer the revalidation and hide the 304.
    response = await fetch(url, {
      method,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'network', "Can't reach Synapse")
  }

  if (response.status === 304 && cached) return cached.data as T
  if (!response.ok) throw await errorFrom(response)
  const data = (await response.json().catch(() => {
    throw new ApiError(response.status, 'bad_response', 'The server sent an unexpected response')
  })) as T
  const etag = response.headers.get('ETag')
  if (revalidate && etag) etags.set(url, { etag, data })
  return data
}
