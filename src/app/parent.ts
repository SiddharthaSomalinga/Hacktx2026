// Where Back goes when the app was opened straight onto a deep link (a QR code or a notification).
export function parentOf(pathname: string): string {
  const parts = pathname.split('/').filter(Boolean)
  if (parts[0] === 'b' && parts.length > 2) return '/' + parts.slice(0, parts.length - 1).join('/')
  if (parts[0] === 'seat' && parts.length > 2) return `/seat/${parts[1]}`
  return '/'
}
