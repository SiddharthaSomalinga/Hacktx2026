/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { parsePayload } from './notify'

declare const self: ServiceWorkerGlobalScope

// The app shell, fonts, map tiles and glyphs, icons and card images: everything to open offline.
// /api is never cached (ARCH §12): live data must come from the server or be shown as stale.
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), { denylist: [/^\/api\//] }))

self.addEventListener('message', (event) => {
  if ((event.data as { type?: string } | null)?.type === 'SKIP_WAITING') void self.skipWaiting()
})
clientsClaim()

self.addEventListener('push', (event) => {
  const shown = parsePayload(event.data?.text())
  event.waitUntil(
    self.registration.showNotification(shown.title, {
      body: shown.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/badge-96.png',
      tag: shown.url,
      data: { url: shown.url },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data as { url?: string } | null)?.url ?? '/'
  event.waitUntil(
    (async () => {
      // Reuse an open Ghost Seats window if there is one; open a new one otherwise.
      const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const open = windows.find((w) => new URL(w.url).origin === self.location.origin)
      if (open) {
        await open.focus()
        open.postMessage({ type: 'navigate', url })
        return
      }
      await self.clients.openWindow(url)
    })(),
  )
})

// The browser rotated the subscription: register the new one with the same session cookie.
self.addEventListener('pushsubscriptionchange', (event) => {
  const change = event as Event & { newSubscription?: PushSubscription | null; waitUntil: (p: Promise<unknown>) => void }
  const next = change.newSubscription
  if (!next) return
  const json = next.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) return
  change.waitUntil(
    fetch('/api/push/subscribe', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } }),
    }),
  )
})
