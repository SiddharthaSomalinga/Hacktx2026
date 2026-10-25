// Mirrors backend/app/config.py `poll_web_s` (FR-10). The backend does not expose it.
export const POLL_WEB_S = 3

// Data older than this is no longer called "Live" (D46).
export const LIVE_FOR_MS = 2 * POLL_WEB_S * 1000

// Longest wait between polls while the backend keeps failing.
export const MAX_BACKOFF_MS = 30_000

// Limits enforced by the API schemas; the inputs enforce them first.
export const TOPIC_MAX = 200
export const ABOUT_ME_MAX = 280
export const REPORT_MAX = 500

export const CENTRAL_TIME = 'America/Chicago'
