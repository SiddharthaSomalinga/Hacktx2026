import { useMutation, useQueryClient } from '@tanstack/react-query'
import { endpoints } from '../../api/endpoints'
import { keys, useMe } from '../../api/queries'
import { resubscribeIfGranted, unsubscribePush } from '../push/subscription'

export function useSession() {
  const me = useMe()
  const client = useQueryClient()
  const login = useMutation({
    mutationFn: endpoints.login,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.me })
      void resubscribeIfGranted() // move this device's push subscription to the new account (D50)
    },
  })
  const logout = useMutation({
    mutationFn: async () => {
      await unsubscribePush() // while still logged in: DELETE needs the session (D50)
      await endpoints.logout()
    },
    onSettled: () => {
      client.removeQueries({ queryKey: ['search'] })
      client.removeQueries({ queryKey: ['match'] })
      client.removeQueries({ queryKey: keys.inbox })
      void client.invalidateQueries({ queryKey: keys.me })
    },
  })
  return { me, user: me.data?.user ?? null, login, logout }
}
