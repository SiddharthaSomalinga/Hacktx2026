import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test'
import { leaveAsFound } from './cleanup'

// A seeker asks to join, the host accepts, and only then does the seeker see where to go
// (FR-43, D43). Two browser contexts, so two separate sessions, through the real UI.
// The stack must run with DEMO_HOSTS=false, so the request reaches the real host.

const NODE_KEY = process.env.NODE_KEY ?? ''
const NODE = 'table-1' // sql/seed.sql: seats t1-s1 and t1-s2, PCL floor 2, Table 01
const SEAT = 't1-s1'
const TABLE = 'Table 01'

/** Plays the node: the host sits on t1-s1 and t1-s2 stays empty. The host must read as present
 * to link the seat, and the table needs an open seat for the host to be findable (FR-24).
 * The returned stop waits for a post in flight: one that outlived the test would reject once
 * Playwright disposes `request`, failing a test that had passed. */
function sensePerson(request: APIRequestContext): () => Promise<void> {
  let running = true
  const post = async () => {
    const r = await request.post('/api/readings', {
      headers: { 'X-Node-Key': NODE_KEY },
      data: {
        node_id: NODE,
        readings: [
          { seat_id: SEAT, object_present: true, human_present: true },
          { seat_id: 't1-s2', object_present: false, human_present: false },
        ],
      },
    })
    expect(r.status(), await r.text()).toBe(200)
  }
  const loop = (async () => {
    while (running) {
      await post()
      await new Promise((resolve) => setTimeout(resolve, 2000))
    }
  })()
  return async () => {
    running = false
    await loop
  }
}

async function loggedIn(browser: Browser, firstName: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/login')
  await page.getByRole('button', { name: new RegExp(`^${firstName}\\b`) }).click()
  await page.waitForURL((url) => url.pathname !== '/login')
  return page
}

test('a request reveals the table only after the host accepts', async ({ browser, request }) => {
  expect(NODE_KEY, 'set NODE_KEY to the stack’s node key').not.toBe('')
  const stopSensing = sensePerson(request)
  let host: Page | undefined
  let seeker: Page | undefined
  try {
    host = await loggedIn(browser, 'Alex')
    await host.goto(`/seat/${SEAT}`)
    await host.getByRole('switch', { name: 'Open to study partners' }).click()
    await host.getByLabel("Today's topic").fill('orgo 1')
    await host.getByRole('button', { name: 'Make me findable' }).click()
    await host.waitForURL('**/host')

    seeker = await loggedIn(browser, 'Priya')
    await seeker.getByPlaceholder('orgo exam, CS 314 trees, macro…').fill('orgo 1')
    await seeker.getByRole('button', { name: 'Find people studying this' }).click()
    await seeker.getByRole('button', { name: 'Ask to join them' }).click()
    const seekerPanel = seeker.getByRole('region', { name: 'Synapse' })
    await expect(seekerPanel).toContainText('Asking Alex · Biochemistry')
    await expect(seekerPanel).not.toContainText(TABLE)

    const card = host.getByRole('article', { name: /^Request from Priya/ })
    await expect(card).toContainText(`at ${TABLE}`) // the host already knows their own table
    await card.getByRole('button', { name: 'Accept' }).click()

    await seeker.waitForURL('**/match/**')
    await expect(seekerPanel).toContainText(`PCL Library · Floor 2 · ${TABLE}`)
  } finally {
    await stopSensing()
    await leaveAsFound(host, seeker)
  }
})
