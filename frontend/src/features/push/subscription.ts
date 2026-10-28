import { endpoints } from '../../api/endpoints'

export type PushSupport = 'supported' | 'needs-install' | 'unsupported'

const standalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true
const isIos = () => /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

/** iOS only allows web push from an app added to the Home Screen (FR-51). */
export function pushSupport(): PushSupport {
  if ('serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window) return 'supported'
  if (isIos() && !standalone()) return 'needs-install'
  return 'unsupported'
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(padded)
  const bytes = new Uint8Array(new ArrayBuffer(raw.length))
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
  return bytes
}

/**
 * The subscribe body: endpoint and keys only. The browser's toJSON() also carries
 * `expirationTime`, which the API's strict schema rejects with a 422.
 */
export function subscribeBody(subscription: PushSubscriptionJSON) {
  const { endpoint, keys } = subscription
  if (!endpoint || !keys?.p256dh || !keys.auth) throw new Error('incomplete push subscription')
  return { endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth } }
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null
  return (await navigator.serviceWorker.getRegistration()) ?? null
}

/** Ask permission (from a tap) and register this device for notifications. */
export async function enablePush(): Promise<'granted' | 'denied' | 'unavailable'> {
  if (pushSupport() !== 'supported') return 'unavailable'
  const reg = await registration()
  if (!reg) return 'unavailable'
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return 'denied'
  const { key } = await endpoints.vapidKey()
  const subscription =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) }))
  await endpoints.subscribe(subscribeBody(subscription.toJSON()))
  return 'granted'
}

export async function pushEnabled(): Promise<boolean> {
  if (pushSupport() !== 'supported' || Notification.permission !== 'granted') return false
  return (await (await registration())?.pushManager.getSubscription()) != null
}

/** After login, send an existing subscription again so it now belongs to this account. */
export async function resubscribeIfGranted(): Promise<void> {
  try {
    if (!(await pushEnabled())) return
    const subscription = await (await registration())?.pushManager.getSubscription()
    if (subscription) await endpoints.subscribe(subscribeBody(subscription.toJSON()))
  } catch {
    // Push is an extra; login never fails because of it (NFR-3 spirit).
  }
}

/** Before logout: remove the subscription server-side, then in the browser. */
export async function unsubscribePush(): Promise<void> {
  try {
    const subscription = await (await registration())?.pushManager.getSubscription()
    if (!subscription) return
    await endpoints.unsubscribe(subscription.endpoint).catch(() => undefined)
    await subscription.unsubscribe()
  } catch {
    // Same: never block logout.
  }
}
