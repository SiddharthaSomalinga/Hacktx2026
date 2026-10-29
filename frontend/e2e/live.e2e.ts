import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { leaveAsFound } from './cleanup'

// The live stream (D61) in a real browser, against the compose stack with DEBOUNCE_S=0:
// changes arrive without polling, and polling comes back only when the stream can't serve.

const NODE_KEY = process.env.NODE_KEY ?? ''
const NODE = 'table-1' // sql/seed.sql: seats t1-s1 and t1-s2, PCL floor 2, Table 01

async function sense(request: APIRequestContext, s1: [boolean, boolean], s2: [boolean, boolean] = [false, false]) {
  const r = await request.post('/api/readings', {
    headers: { 'X-Node-Key': NODE_KEY },
    data: {
      node_id: NODE,
      readings: [
        { seat_id: 't1-s1', object_present: s1[0], human_present: s1[1] },
        { seat_id: 't1-s2', object_present: s2[0], human_present: s2[1] },
      ],
    },
  })
  expect(r.status(), await r.text()).toBe(200)
}

/** Every API path the page requests from now on. */
function recordApi(page: Page): string[] {
  const paths: string[] = []
  page.on('request', (r) => {
    const url = new URL(r.url())
    if (url.pathname.startsWith('/api/')) paths.push(url.pathname)
  })
  return paths
}

test.beforeEach(() => {
  expect(NODE_KEY, 'set NODE_KEY to the stack’s node key').not.toBe('')
})

test('a seat change reaches the floor plan without any polling', async ({ page, request }) => {
  await sense(request, [false, false])
  await page.goto('/b/pcl/2/pcl-2-t1') // the table, so its chairs are buttons
  const seat = page.getByRole('button', { name: /^Table 01 seat 1, / })
  await expect(seat).toHaveAccessibleName(/, open$/)
  await page.waitForTimeout(4_000) // longer than one poll interval, with the stream open
  const api = recordApi(page)

  const changed = Date.now()
  await sense(request, [true, true])
  await expect(seat).toHaveAccessibleName(/, occupied$/, { timeout: 2_000 })
  const shownAfter = Date.now() - changed
  await page.waitForTimeout(4_000)

  expect(api.filter((p) => p.startsWith('/api/buildings'))).toEqual([])
  await expect(page.getByRole('status').filter({ hasText: 'Live' })).toBeVisible()
  test.info().annotations.push({ type: 'seat change shown after', description: `${shownAfter} ms` })
})

test('a logged-out visitor never polls who they are', async ({ page }) => {
  await page.goto('/')
  await page.waitForTimeout(1_000)
  const api = recordApi(page)
  await page.waitForTimeout(10_000)
  expect(api.filter((p) => p === '/api/me')).toEqual([])
  expect(api.filter((p) => p.startsWith('/api/buildings'))).toEqual([])
})

test('a host sees a request arrive without polling the inbox', async ({ browser, request }) => {
  const heartbeat = setInterval(() => void sense(request, [true, true]).catch(() => {}), 2_000)
  const host = await (await browser.newContext()).newPage()
  const seeker = await (await browser.newContext()).newPage()
  try {
    await sense(request, [true, true])
    await host.goto('/login')
    await host.getByRole('button', { name: /^Alex\b/ }).click()
    await host.waitForURL((url) => url.pathname !== '/login')
    await host.goto('/seat/t1-s1')
    await host.getByRole('switch', { name: 'Open to study partners' }).click()
    await host.getByLabel("Today's topic").fill('orgo 1')
    await host.getByRole('button', { name: 'Make me findable' }).click()
    await host.waitForURL('**/host')
    await host.waitForTimeout(4_000)
    const api = recordApi(host)

    await seeker.goto('/login')
    await seeker.getByRole('button', { name: /^Priya\b/ }).click()
    await seeker.waitForURL((url) => url.pathname !== '/login')
    await seeker.getByPlaceholder('orgo exam, CS 314 trees, macro…').fill('orgo 1')
    await seeker.getByRole('button', { name: 'Find people studying this' }).click()
    await seeker.getByRole('button', { name: 'Ask to join them' }).click()

    await expect(host.getByRole('article', { name: /^Request from Priya/ })).toBeVisible({ timeout: 5_000 })
    const fetchedOnHint = api.filter((p) => p === '/api/host/inbox').length
    expect(fetchedOnHint).toBeGreaterThan(0) // the hint made it refetch
    await host.waitForTimeout(8_000)
    expect(api.filter((p) => p === '/api/host/inbox').length).toBe(fetchedOnHint) // and nothing since
  } finally {
    clearInterval(heartbeat)
    await leaveAsFound(host, seeker)
  }
})

test('without the stream, the app polls as before and stays live', async ({ page }) => {
  await page.route('**/api/live**', (route) => route.abort())
  await page.goto('/b/pcl/2')
  await page.waitForTimeout(1_000)
  const api = recordApi(page)
  await page.waitForTimeout(12_000)
  const polls = api.filter((p) => p === '/api/buildings/pcl').length
  expect(polls).toBeGreaterThanOrEqual(2) // every POLL_WEB_S once LIVE_FOR_MS passed
  await expect(page.getByRole('status').filter({ hasText: 'Live' })).toBeVisible()
})
