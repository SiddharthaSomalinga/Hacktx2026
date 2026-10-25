import { Outlet } from 'react-router'
import { AnnouncerProvider } from '../ui/Announcer'
import { Panel } from '../ui/Panel'
import { UpdatePrompt } from '../features/pwa/UpdatePrompt'
import { Canvas } from './Canvas'
import { FocusProvider } from './focus'
import { LiveBar } from './LiveBar'
import { TopBar } from './TopBar'

/** One canvas stays mounted on every route; child routes change the panel and what it shows (D46). */
export function Layout() {
  return (
    <AnnouncerProvider>
      <FocusProvider>
        <Canvas />
        <TopBar />
        <Panel label="Ghost Seats">
          <LiveBar />
          <Outlet />
        </Panel>
        <UpdatePrompt />
      </FocusProvider>
    </AnnouncerProvider>
  )
}
