import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { RouterProvider } from 'react-router'
import { makeQueryClient, PUBLIC_QUERY_ROOTS } from '../api/queries'
import { safeStorage } from '../lib/storage'
import { router } from './router'

const queryClient = makeQueryClient()

// Only public map data is kept across reloads, so an offline reopen still shows the last map with
// its age. Nothing personal (me, searches, matches, inbox) is ever written to storage.
const persister = createSyncStoragePersister({ storage: safeStorage('local'), key: 'gs-map-cache' })

export function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: 24 * 60 * 60 * 1000,
        buster: 'v2',
        dehydrateOptions: {
          shouldDehydrateQuery: (query) =>
            query.state.status === 'success' && PUBLIC_QUERY_ROOTS.has(String(query.queryKey[0])),
        },
      }}
    >
      <RouterProvider router={router} />
    </PersistQueryClientProvider>
  )
}
