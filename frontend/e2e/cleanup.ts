import type { Page } from '@playwright/test'

/**
 * Leaves the stack as a test found it. The tests share one stack and its demo users (Alex
 * hosts, Priya seeks), so a search, match or open host left behind would break the next test.
 * Each step is skipped when its page never got that far.
 */
export async function leaveAsFound(host: Page | undefined, seeker: Page | undefined): Promise<void> {
  if (seeker) {
    const me = (await (await seeker.request.get('/api/me')).json()) as { search_id: string | null; match_id: string | null }
    if (me.match_id) await seeker.request.post(`/api/matches/${me.match_id}/cancel`)
    if (me.search_id) await seeker.request.post(`/api/search/${me.search_id}/cancel`)
  }
  if (host) await host.request.post('/api/host/toggle', { data: { open: false } })
}
