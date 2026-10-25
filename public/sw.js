self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))
self.addEventListener('push', (event) => {
  const data = event.data?.json() || { title: 'Ghost Seats', body: 'You have a new study request.' }
  event.waitUntil(self.registration.showNotification(data.title || 'Ghost Seats', { body: data.body, data: data.url || '/' }))
})
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  event.waitUntil(clients.openWindow(event.notification.data || '/'))
})
