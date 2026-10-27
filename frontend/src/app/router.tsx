import { createBrowserRouter } from 'react-router'
import { LoginScreen } from '../features/account/LoginScreen'
import { BuildingRedirect, FloorScreen } from '../features/building/FloorScreen'
import { HistoryScreen } from '../features/building/HistoryScreen'
import { HomeScreen } from '../features/home/HomeScreen'
import { HostScreen } from '../features/host/HostScreen'
import { HostSetupScreen } from '../features/host/HostSetupScreen'
import { SeatScreen } from '../features/host/SeatScreen'
import { MatchScreen } from '../features/match/MatchScreen'
import { FindScreen } from '../features/seeker/FindScreen'
import { SearchScreen } from '../features/seeker/SearchScreen'
import { Layout } from './Layout'
import { NotFound, RouteError } from './RouteError'

// Every step of every flow has a URL (D46). Push notifications open /host, /match/:id and
// /search/:id; seat QR codes open /seat/:id.
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <HomeScreen /> },
      { path: 'b/:buildingId', element: <BuildingRedirect /> },
      { path: 'b/:buildingId/history', element: <HistoryScreen /> },
      { path: 'b/:buildingId/:floor', element: <FloorScreen /> },
      { path: 'b/:buildingId/:floor/:tableId', element: <FloorScreen /> },
      { path: 'seat/:seatId', element: <SeatScreen /> },
      { path: 'seat/:seatId/host', element: <HostSetupScreen /> },
      { path: 'host', element: <HostScreen /> },
      { path: 'login', element: <LoginScreen /> },
      { path: 'find', element: <FindScreen /> },
      { path: 'search/:searchId', element: <SearchScreen /> },
      { path: 'match/:matchId', element: <MatchScreen /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
