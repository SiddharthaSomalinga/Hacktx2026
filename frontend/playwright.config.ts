import { defineConfig, devices } from '@playwright/test'

// Browser tests against a running stack: compose.yaml plus compose.e2e.yaml at the repo root
// (docs/TESTING.md). Nothing here starts a server.
export default defineConfig({
  testDir: 'e2e',
  testMatch: '**/*.e2e.ts', // not *.spec.ts, so Vitest never picks these up
  timeout: 90_000,
  // One at a time: every test plays the same sensor node and logs in as the same demo users.
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    ...devices['Pixel 7'], // phone-first (NFR-4)
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
    trace: 'retain-on-failure',
  },
})
