import { Outlet } from 'react-router'
import { AnnouncerProvider } from '../ui/Announcer'
import { Panel } from '../ui/Panel'
import { UpdatePrompt } from '../features/pwa/UpdatePrompt'
import { Canvas } from './Canvas'
import { FocusProvider } from './focus'
import { LiveBar } from './LiveBar'
import { TopBar } from './TopBar'
import { useLive } from './useLive'

/** Holds the live stream open (D61); inside FocusProvider, which says which building to carry. */
function LiveStream() {
  useLive()
  return null
}

/** One canvas stays mounted on every route; child routes change the panel and what it shows (D46). */
export function Layout() {
  return (
    <AnnouncerProvider>
      <FocusProvider>
        <LiveStream />
        <Canvas />
        <TopBar />
        <Panel label="Synapse">
          <LiveBar />
          <Outlet />
        </Panel>
        <UpdatePrompt />
      </FocusProvider>
    </AnnouncerProvider>
  )
}
