import { useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import * as maplibregl from 'maplibre-gl'
import {
  ArrowUpRight, Bell, BookOpen, Check, ChevronDown, Clock3, Compass,
  MapPin, Menu, MessageCircle, Moon, Search, Send, Sparkles, Sun, UserRound, Users, X, Zap,
} from 'lucide-react'
import { api } from './api'
import './styles.css'
import 'maplibre-gl/dist/maplibre-gl.css'

const seedBuildings = [
  { id: 'pcl', name: 'PCL Library', short: 'P', distance: '4 min walk', floors: 4, open: 62, total: 104, status: 'live', color: 'green', location: 'East Mall' },
  { id: 'union', name: 'Texas Union', short: 'U', distance: '7 min walk', floors: 3, open: 28, total: 61, status: 'live', color: 'blue', location: '21st Street' },
  { id: 'gdc', name: 'GDC Study Hall', short: 'G', distance: '9 min walk', floors: 2, open: 41, total: 78, status: 'simulated', color: 'yellow', location: 'Robert Dedman Dr' },
  { id: 'sac', name: 'Student Activity Center', short: 'S', distance: '12 min walk', floors: 2, open: 19, total: 54, status: 'simulated', color: 'coral', location: 'Robert Dedman Dr' },
]

const seedSeats = [
  ['A1', 'open'], ['A2', 'occupied'], ['A3', 'open'], ['A4', 'likely'], ['A5', 'open'], ['A6', 'away'],
  ['B1', 'open'], ['B2', 'open'], ['B3', 'occupied'], ['B4', 'open'], ['B5', 'offline'], ['B6', 'open'],
  ['C1', 'likely'], ['C2', 'open'], ['C3', 'open'], ['C4', 'occupied'], ['C5', 'open'], ['C6', 'open'],
  ['D1', 'open'], ['D2', 'away'], ['D3', 'open'], ['D4', 'open'], ['D5', 'likely'], ['D6', 'open'],
]

function App() {
  const [view, setView] = useState('map')
  const [buildings, setBuildings] = useState(seedBuildings)
  const [selectedBuilding, setSelectedBuilding] = useState(seedBuildings[0])
  const [buildingDetail, setBuildingDetail] = useState(null)
  const [history, setHistory] = useState([])
  const [selectedSeat, setSelectedSeat] = useState(null)
  const [floor, setFloor] = useState(2)
  const [query, setQuery] = useState('')
  const [topic, setTopic] = useState('')
  const [user, setUser] = useState(null)
  const [notice, setNotice] = useState('')
  const [showLogin, setShowLogin] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [demoUsers, setDemoUsers] = useState([])
  const [showTopic, setShowTopic] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [hostOpen, setHostOpen] = useState(false)
  const [host, setHost] = useState(null) // the server's host session: {seat_id, label, status, hidden_reason, muted}
  const [searching, setSearching] = useState(false)
  const [search, setSearch] = useState(null) // {id, label, status, seconds_left}
  const [matchId, setMatchId] = useState(null)
  const [match, setMatch] = useState(null)
  const [inbox, setInbox] = useState([])
  const [darkMode, setDarkMode] = useState(() => window.localStorage.getItem('ghost-seats-theme') === 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = darkMode ? 'dark' : 'light'
    window.localStorage.setItem('ghost-seats-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])

  useEffect(() => {
    api.me().then((data) => data?.user && setUser(data.user)).catch(() => {})
    api.demoUsers().then((users) => setDemoUsers(users || [])).catch(() => {})
    api.buildings().then((data) => {
      if (data?.length) {
        setBuildings(data)
        setSelectedBuilding((current) => data.find((building) => building.id === current.id) || data[0])
      }
    }).catch(() => {})
    const interval = window.setInterval(() => api.buildings().then((data) => data?.length && setBuildings(data)).catch(() => {}), 2000)
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {})
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!selectedBuilding?.id) return undefined
    const loadDetail = () => {
      api.building(selectedBuilding.id).then((data) => {
        if (data) {
          setBuildingDetail(data)
          if (data.floors?.length && !data.floors.some((item) => item.floor === floor)) setFloor(data.floors[0].floor)
        }
      }).catch(() => setBuildingDetail(null))
    }
    loadDetail()
    const detailTimer = window.setInterval(loadDetail, 1500)
    return () => window.clearInterval(detailTimer)
  }, [selectedBuilding?.id, floor])

  useEffect(() => {
    if (view !== 'history' || !selectedBuilding?.id) return undefined
    api.history(selectedBuilding.id).then(setHistory).catch(() => setHistory([]))
    return undefined
  }, [view, selectedBuilding?.id])

  // The server is the source of truth for roles: poll who we are, what we host, what we're in.
  useEffect(() => {
    if (!user) return undefined
    refreshMe()
    const timer = window.setInterval(refreshMe, 3000)
    return () => window.clearInterval(timer)
  }, [user?.id])

  useEffect(() => {
    if (!host) { setInbox([]); return undefined }
    const load = () => api.inbox().then((items) => setInbox(items || [])).catch(() => {})
    load()
    const timer = window.setInterval(load, 3000)
    return () => window.clearInterval(timer)
  }, [host?.session_id])

  useEffect(() => {
    if (!search?.id) return undefined
    const poll = () => api.searchStatus(search.id).then((result) => {
      if (result.match_id) { setSearch(null); setSearching(false); openMatch(result.match_id) }
      else if (result.status === 'exhausted') { setSearch(null); setSearching(false); setNotice('No one’s free right now. Try a recommended seat.') }
      else if (result.status !== 'active') { setSearch(null); setSearching(false) }
      else setSearch((current) => current && { ...current, seconds_left: result.seconds_left })
    }).catch(() => {})
    const timer = window.setInterval(poll, 2000)
    return () => window.clearInterval(timer)
  }, [search?.id])

  useEffect(() => {
    if (!matchId) return undefined
    const load = () => api.match(matchId).then(setMatch).catch(() => {})
    load()
    const timer = window.setInterval(load, 2000)
    return () => window.clearInterval(timer)
  }, [matchId])

  useEffect(() => {
    if (!notice) return undefined
    const timeout = window.setTimeout(() => setNotice(''), 3200)
    return () => window.clearTimeout(timeout)
  }, [notice])

  const filteredBuildings = buildings.filter((building) => `${building.name} ${building.location}`.toLowerCase().includes(query.toLowerCase()))
  const openSeats = useMemo(() => buildings.reduce((total, building) => total + (building.open || 0), 0) || seedSeats.filter(([, status]) => status === 'open').length, [buildings])

  function chooseBuilding(building) { setSelectedBuilding(building); setView('map'); setNotice(`${building.name} selected`) }
  function login(userId) {
    api.login({ user_id: userId }).then((nextUser) => {
      setUser(nextUser); setShowLogin(false); setShowTopic(true)
    }).catch(() => setNotice('Unable to sign in'))
  }
  function refreshMe() {
    return api.me().then((data) => {
      setHost(data?.host || null)
      if (data?.host) setHostOpen(true)
      if (data?.search_id) setSearch((current) => current || { id: data.search_id, status: 'active' })
      if (data?.match_id) setMatchId((current) => {
        if (current !== data.match_id) setView('match')
        return data.match_id
      })
    }).catch(() => {})
  }
  function openMatch(id) { setMatchId(id); setView('match') }
  function saveTopic() {
    const nextTopic = topic.trim()
    setShowTopic(false)
    if (user) setUser({ ...user, topic: nextTopic })
    if (!nextTopic) { setNotice('Topic skipped'); return }
    // A seeker's topic goes into their search; only a linked host stores it on the server.
    if (!host) { setNotice(`Studying ${nextTopic}`); return }
    api.topic(nextTopic).then((result) => { setNotice(`Studying ${result.label}`); refreshMe() }).catch((error) => setNotice(error.message))
  }
  async function startSearch() {
    setShowSearch(false); setSearching(true)
    try {
      const result = await api.search(user?.topic || topic || 'anything')
      if (!result.has_real_hosts) {
        await api.cancelSearch(result.search_id)
        setSearching(false); setNotice(`No one studying ${result.label} can take a request right now`)
        return
      }
      const joined = await api.joinSearch(result.search_id)
      setSearch({ id: result.search_id, label: result.label, status: joined.status, seconds_left: joined.seconds_left })
      setNotice(`Asking someone studying ${result.label}`)
    } catch (error) {
      setSearching(false); setNotice(error.message)
    }
  }
  function cancelSearch() {
    if (!search?.id) return
    api.cancelSearch(search.id).finally(() => { setSearch(null); setSearching(false); setNotice('Search cancelled') })
  }
  function linkSeat(seatId) {
    api.linkSeat(seatId)
      .then(() => (user?.topic || topic.trim()) && api.topic(user?.topic || topic.trim()))
      .then(() => { setSelectedSeat(seatId); setNotice(`Linked to seat ${seatId}`); return refreshMe() })
      .catch((error) => setNotice(error.message))
  }
  function toggleHost(open) {
    // D17: turning host mode on only opens setup; linking a seat creates the session.
    if (open || !host) { setHostOpen(open); return }
    api.toggleHost(false).then(() => { setHost(null); setHostOpen(false); setNotice('Host mode off') }).catch((error) => setNotice(error.message))
  }
  function answerRequest(requestId, action) {
    const call = action === 'accept' ? api.acceptRequest(requestId) : api.declineRequest(requestId, action === 'mute')
    call.then((result) => {
      setInbox((items) => items.filter((item) => item.request_id !== requestId))
      if (action === 'accept') openMatch(result.match_id)
      else { setNotice(action === 'mute' ? 'Request declined and muted' : 'Request declined'); refreshMe() }
    }).catch((error) => setNotice(error.message))
  }
  function finishMatch(action) {
    const call = action === 'arrived' ? api.arrived(matchId) : api.cancelMatch(matchId)
    call.then(() => api.match(matchId)).then(setMatch).catch((error) => setNotice(error.message))
  }
  function leaveMatch() { setMatchId(null); setMatch(null); setView('map'); refreshMe() }
  function logout() {
    api.logout().catch(() => {})
    setUser(null); setHost(null); setHostOpen(false); setSearch(null); setSearching(false); setMatchId(null); setMatch(null); setInbox([])
    setNotice('Signed out')
  }

  return <div className="app-shell">
    <header className="topbar">
      <button className="brand" onClick={() => setView('map')} aria-label="Ghost Seats home"><span className="brand-mark"><span /></span><span>ghost seats</span></button>
      <nav className="desktop-nav" aria-label="Primary navigation"><button className={view === 'map' ? 'nav-link active' : 'nav-link'} onClick={() => setView('map')}>Find a seat</button><button className={view === 'history' ? 'nav-link active' : 'nav-link'} onClick={() => setView('history')}>History</button><button className={view === 'host' ? 'nav-link active' : 'nav-link'} onClick={() => setView('host')}>Host mode</button></nav>
      <div className="top-actions"><button className="icon-button theme-button" onClick={() => setDarkMode((current) => !current)} aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'} title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}>{darkMode ? <Sun size={18} /> : <Moon size={18} />}</button><button className="icon-button notification-button" onClick={() => setView('inbox')} aria-label="Open inbox"><Bell size={18} />{inbox.length > 0 && <i />}</button>{user ? <button className="profile-chip" onClick={() => setMenuOpen((open) => !open)}><span>{user.first_name[0]}</span>{user.first_name}<ChevronDown size={14} /></button> : <button className="login-button" onClick={() => setShowLogin(true)}>Log in <ArrowUpRight size={16} /></button>}<button className="mobile-menu icon-button" aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button></div>
    </header>
    {menuOpen && <nav className="menu-panel" aria-label="Menu">
      {[['map', 'Find a seat'], ['history', 'History'], ['host', 'Host mode'], ['inbox', 'Inbox']].map(([target, label]) => <button key={target} className={view === target ? 'active' : ''} onClick={() => { setView(target); setMenuOpen(false) }}>{label}</button>)}
      {user ? <button onClick={() => { logout(); setMenuOpen(false) }}>Log out {user.first_name}</button> : <button onClick={() => { setShowLogin(true); setMenuOpen(false) }}>Log in</button>}
    </nav>}
    {view === 'map' && <MapView buildings={filteredBuildings} selectedBuilding={selectedBuilding} chooseBuilding={chooseBuilding} floor={floor} setFloor={setFloor} selectedSeat={selectedSeat} setSelectedSeat={setSelectedSeat} query={query} setQuery={setQuery} openSeats={openSeats} buildingDetail={buildingDetail} />}
    {view === 'history' && <HistoryView building={selectedBuilding} points={history} />}
    {view === 'host' && <HostView user={user} host={host} hostOpen={hostOpen} topic={user?.topic || topic} seatId={selectedSeat || 't1-s1'} onLogin={() => setShowLogin(true)} onToggleHost={toggleHost} onLinkSeat={linkSeat} onEditTopic={() => setShowTopic(true)} onMute={(muted) => api.muteHost(muted).then(refreshMe).catch((error) => setNotice(error.message))} onConfirm={() => api.confirmHost().then(refreshMe).catch((error) => setNotice(error.message))} />}
    {view === 'inbox' && <InboxView inbox={inbox} hosting={Boolean(host)} onAnswer={answerRequest} />}
    {view === 'match' && <MatchView match={match} onBack={leaveMatch} onAction={finishMatch} />}
    <section className="action-strip">{search ? <><div><span className="eyebrow">Looking for a study partner</span><strong>Asking someone studying {search.label || 'your topic'}{search.seconds_left ? ` · ${search.seconds_left}s left` : ''}</strong></div><button className="primary-button" onClick={cancelSearch}><X size={17} /> Cancel search</button></> : <><div><span className="eyebrow">Make the next hour count</span><strong>Find a study partner who is already here.</strong></div><button className="primary-button" disabled={searching || Boolean(host) || match?.status === 'active'} onClick={() => user ? setShowSearch(true) : setShowLogin(true)}><Users size={17} /> {host ? 'Hosting now' : match?.status === 'active' ? 'In a match' : 'Find someone'} <ArrowUpRight size={16} /></button></>}</section>
    <footer className="footer"><span>Ghost Seats · UT Austin</span><span>Live occupancy · Central Time</span><span><Compass size={14} /> Built for the in-between moments</span></footer>
    {showLogin && <Modal title="Welcome to Ghost Seats" onClose={() => setShowLogin(false)}><p className="modal-copy">Choose a demo identity to explore the seeker and host flows.</p><div className="identity-list">{demoUsers.length ? demoUsers.map((demo) => <button key={demo.id} className="identity-row" onClick={() => login(demo.id)}><span className="avatar">{demo.first_name[0]}</span><span><strong>{demo.first_name}</strong><small>UT Austin student</small></span><ArrowUpRight size={16} /></button>) : <p className="modal-copy">Demo users are loading…</p>}</div></Modal>}
    {showTopic && <Modal title="What are you studying today?" onClose={() => setShowTopic(false)}><p className="modal-copy">A topic helps us find a useful match. You can skip this for now.</p><div className="topic-input"><BookOpen size={18} /><input autoFocus value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="e.g. organic chemistry" onKeyDown={(event) => event.key === 'Enter' && saveTopic()} /></div><div className="modal-actions"><button className="quiet-button" onClick={() => { setShowTopic(false); setNotice('Topic skipped') }}>Skip for now</button><button className="primary-button" onClick={saveTopic}>Save topic <Check size={16} /></button></div></Modal>}
    {showSearch && <Modal title="Find someone studying nearby" onClose={() => setShowSearch(false)}><p className="modal-copy">We’ll look for a real host in the same subject group. No names appear until you both accept.</p><div className="search-topic"><label>Subject</label><strong>{user?.topic || 'Anything goes'}</strong><span>Same course first, related topics second</span></div><div className="modal-actions"><button className="quiet-button" onClick={() => setShowSearch(false)}>Not now</button><button className="primary-button" onClick={startSearch}>{searching ? 'Searching...' : 'Start looking'} <Send size={15} /></button></div></Modal>}
    {notice && <div className="toast"><Check size={15} />{notice}</div>}
  </div>
}

function MapView({ buildings, selectedBuilding, chooseBuilding, floor, setFloor, selectedSeat, setSelectedSeat, query, setQuery, openSeats, buildingDetail }) {
  return <main><section className="hero"><div className="hero-copy"><span className="eyebrow"><span className="live-dot" /> Austin campus · updated just now</span><h1>Start anywhere.<br /><em>Find your table.</em></h1><p>See what’s actually vacant, then find someone studying the same thing.<br />No wandering. No awkward cold starts.</p></div><div className="hero-note"><Sparkles size={17} /><span><strong>{openSeats} vacant seats</strong><br />across the campus right now</span></div></section>
    <section className="campus-section"><div className="section-heading"><div><span className="eyebrow">Campus map <span className="muted-separator">/</span> UT Austin · Main campus</span><h2>Start anywhere on campus.</h2><p>Search a building to jump from the quad to its live classroom map.</p></div><div className="search-box"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search buildings, libraries..." /><kbd>⌘ K</kbd></div></div><CampusMap buildings={buildings} selectedBuilding={selectedBuilding} chooseBuilding={chooseBuilding} /></section>
    <section className="workspace"><aside className="building-list"><div className="list-heading"><span className="eyebrow">Nearby buildings</span><span>Updated just now</span></div>{buildings.map((building) => <button className={`building-row ${selectedBuilding.id === building.id ? 'selected' : ''}`} key={building.id} onClick={() => chooseBuilding(building)}><span className={`building-icon ${building.color}`}>{building.short}</span><span className="building-meta"><strong>{building.name}</strong><small>{building.distance} · {building.floors} floors</small></span><span className="building-count"><strong>{building.open}</strong><small>open</small></span></button>)}</aside><SeatMap building={selectedBuilding} detail={buildingDetail} floor={floor} setFloor={setFloor} selectedSeat={selectedSeat} setSelectedSeat={setSelectedSeat} /></section></main>
}

const campusCoordinates = {
  pcl: [-97.7343, 30.2837],
  union: [-97.7417, 30.2848],
  gdc: [-97.7274, 30.2847],
  sac: [-97.7397, 30.2815],
}

const fallbackMapStyle = {
  version: 8,
  sources: {
    basemap: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      attribution: 'Tiles &copy; Esri',
    },
    campus: {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: [
          ['pcl', -97.7343, 30.2837, 4, 0.00045, 0.0003],
          ['union', -97.7417, 30.2848, 3, 0.00035, 0.00024],
          ['gdc', -97.7274, 30.2847, 2, 0.00032, 0.00022],
          ['sac', -97.7397, 30.2815, 2, 0.0003, 0.00025],
        ].map(([id, longitude, latitude, floors, width, height]) => ({
          type: 'Feature',
          properties: { id, height: floors * 5, base: 0 },
          geometry: {
            type: 'Polygon',
            coordinates: [[
              [longitude - width, latitude - height],
              [longitude + width, latitude - height],
              [longitude + width, latitude + height],
              [longitude - width, latitude + height],
              [longitude - width, latitude - height],
            ]],
          },
        })),
      },
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#e8e2dc' } },
    { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': 0.9 } },
    {
      id: 'campus-buildings',
      type: 'fill-extrusion',
      source: 'campus',
      paint: {
        'fill-extrusion-color': '#bf5700',
        'fill-extrusion-height': ['get', 'height'],
        'fill-extrusion-base': ['get', 'base'],
        'fill-extrusion-opacity': 0.88,
      },
    },
  ],
}

function CampusMap({ buildings, selectedBuilding, chooseBuilding }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return undefined
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: import.meta.env.VITE_MAP_STYLE_URL || fallbackMapStyle,
      center: [-97.735, 30.284],
      zoom: 15.2,
      pitch: 58,
      bearing: -18,
      attributionControl: false,
    })
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right')
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.on('error', (event) => console.error('MapLibre map error', event.error))
    map.on('load', () => {
      if (map.getLayer('campus-buildings') || !map.getSource('openmaptiles')) return
      map.addLayer({
        id: '3d-buildings',
        type: 'fill-extrusion',
        source: 'openmaptiles',
        'source-layer': 'building',
        minzoom: 14,
        paint: {
          'fill-extrusion-color': '#c46a24',
          'fill-extrusion-height': ['coalesce', ['get', 'render_height'], ['get', 'height'], 12],
          'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], ['get', 'min_height'], 0],
          'fill-extrusion-opacity': 0.82,
        },
      })
    })
    mapRef.current = map
    return () => {
      markersRef.current.forEach((marker) => marker.remove())
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return undefined
    markersRef.current.forEach((marker) => marker.remove())
    markersRef.current = buildings.flatMap((building) => {
      const coordinates = campusCoordinates[building.id]
      if (!coordinates) return []
      const element = document.createElement('button')
      element.type = 'button'
      element.className = `map-marker${selectedBuilding?.id === building.id ? ' selected' : ''}`
      element.textContent = building.name
      element.addEventListener('click', () => {
        chooseBuilding(building)
        map.flyTo({ center: coordinates, zoom: 17.2, pitch: 65, duration: 900 })
      })
      return [new maplibregl.Marker({ element, anchor: 'bottom' }).setLngLat(coordinates).addTo(map)]
    })
    return undefined
  }, [buildings, chooseBuilding, selectedBuilding?.id])

  return <><div ref={containerRef} className="map-stage" /><div className="map-legend"><span><i className="legend-live" /> Live building data</span><span><i className="legend-simulated" /> OpenStreetMap 3D buildings</span><span className="map-scale">UT Austin · Main campus</span></div></>
}

function SeatMap({ building, detail, floor, setFloor, selectedSeat, setSelectedSeat }) {
  const floorData = detail?.floors?.find((item) => item.floor === floor)
  const liveSeats = floorData?.tables?.flatMap((table) => table.seats.map((seat) => [seat.id, seat.state]))
  const seats = liveSeats?.length ? liveSeats : seedSeats
  const counts = seats.reduce((result, [, status]) => ({ ...result, [status]: (result[status] || 0) + 1 }), {})
  return <div className="seat-panel"><div className="seat-heading"><div><span className="eyebrow">Seat map <span className="live-pill"><span /> Live</span></span><h2>{building.name}</h2><p>Floor {floor} <span>·</span> Occupancy from seat nodes</p></div><label className="floor-select">Floor {floor}<select value={floor} onChange={(event) => setFloor(Number(event.target.value))}>{(detail?.floors || Array.from({ length: building.floors }, (_, index) => ({ floor: index + 1 }))).map((item) => <option key={item.floor} value={item.floor}>Floor {item.floor}</option>)}</select><ChevronDown size={15} /></label></div><div className="seat-toolbar"><span><i className="seat-key open" />Open <strong>{counts.open || 0}</strong></span><span><i className="seat-key occupied" />Occupied <strong>{counts.occupied || 0}</strong></span><span><i className="seat-key likely" />Likely open <strong>{counts.likely_opening || counts.likely || 0}</strong></span><span className="toolbar-note">Click a seat for details</span></div><div className="seat-canvas"><div className="table-label label-one">Window bar</div><div className="table-label label-two">Group tables</div><div className="seat-grid">{seats.map(([id, status]) => <button key={id} className={`seat ${status} ${selectedSeat === id ? 'selected' : ''}`} onClick={() => setSelectedSeat(id)}><span>{id}</span>{status === 'open' && <i />}</button>)}</div><div className="seat-annotation"><Zap size={14} /> Seats pulse when a recommendation is ready</div></div>{selectedSeat && <div className="seat-detail"><div><span className={`seat-status ${seats.find(([id]) => id === selectedSeat)?.[1]}`}>{selectedSeat}</span><strong>{selectedSeat === 'A4' ? 'Recommended for you' : 'Table seat'}</strong><small>{selectedSeat === 'A4' ? 'Good light · quiet corner · likely open' : `Floor ${floor} · Group tables`}</small></div><button className="primary-button small" onClick={() => setSelectedSeat(null)}>Close <X size={14} /></button></div>}</div>
}

function HistoryView({ building, points }) {
  const average = points.length ? Math.round(points.reduce((total, point) => total + point.open_avg, 0) / points.length) : 54
  return <main className="simple-page"><span className="eyebrow">Seat history · last 24 hours</span><h1>When is {building.name} easiest to find?</h1><p className="lede">A quiet pattern is more useful than a perfect guess.</p><div className="history-card"><div className="chart-meta"><span>Average open seats</span><strong>{average} <small>seats</small></strong><em>{points.length ? 'Live history' : 'Waiting for history'}</em></div><div className="chart"><div className="chart-line" /><div className="chart-area" />{['12am', '4am', '8am', '12pm', '4pm', '8pm', 'now'].map((label) => <span key={label}>{label}</span>)}</div></div><div className="history-insight"><Sparkles size={18} /><div><strong>{points.length ? 'History is ready for this building.' : 'History will appear after occupancy data is recorded.'}</strong><span>Use the live seat map for the latest availability.</span></div></div></main>
}

const hostStatusText = {
  findable: ['Findable', 'Your seat is visible.', 'We’ll only send one request at a time.'],
  needs_topic: ['Hidden', 'Add a topic to be findable.', 'Tell us what you’re studying.'],
  away: ['Hidden', 'No one is at your seat.', 'Sit back down to be findable again.'],
  muted: ['Muted', 'Requests are paused.', 'Unmute when you’re ready for a partner.'],
  table_full: ['Hidden', 'Your table has no open seat.', 'You’ll be findable when a seat frees up.'],
  in_match: ['In a match', 'Someone is on the way.', 'Open your match for the details.'],
  confirm_pending: ['Hidden', 'Still open to partners?', 'Confirm to stay findable.'],
}

function HostView({ user, host, hostOpen, topic, seatId, onLogin, onToggleHost, onLinkSeat, onEditTopic, onMute, onConfirm }) {
  if (!user) return <main className="simple-page host-page"><span className="eyebrow">Host mode</span><h1>Make your seat easier<br /><em>to find.</em></h1><div className="empty-state"><UserRound size={25} /><strong>Log in to become a host.</strong><span>Your identity stays private until you accept a request.</span><button className="primary-button" onClick={onLogin}>Log in <ArrowUpRight size={15} /></button></div></main>
  const state = host ? (host.status === 'findable' ? 'findable' : host.hidden_reason) : null
  const [badge, title, detail] = state ? hostStatusText[state] || hostStatusText.needs_topic : ['Off', hostOpen ? 'Set up your seat.' : 'You are off the map.', hostOpen ? 'Link the seat you’re sitting at, then add a topic.' : 'Turn on host mode when you’re ready.']
  return <main className="simple-page host-page"><span className="eyebrow">Host mode</span><h1>Make your seat easier<br /><em>to find.</em></h1><p className="lede">Let one person studying something similar join you. You’re always in control.</p>
    <div className="host-card"><div className="host-card-top"><div><span className="status-badge"><span className={state === 'findable' ? 'on' : ''} />{badge}</span><h2>{title}</h2><p>{detail}</p></div><button className={`toggle ${hostOpen ? 'on' : ''}`} onClick={() => onToggleHost(!hostOpen)} aria-label="Toggle host mode"><span /></button></div>
      {hostOpen && <div className="host-steps">
        <div className={host ? 'host-step complete' : 'host-step'}><span>{host ? <Check size={15} /> : '1'}</span><div><strong>Link your seat</strong><small>{host ? `Seat ${host.seat_id}` : `Sit at your seat, then link it (${seatId})`}</small></div>{!host && <button className="text-button" onClick={() => onLinkSeat(seatId)}>Link seat <ArrowUpRight size={14} /></button>}</div>
        <div className={host?.label ? 'host-step complete' : 'host-step'}><span>{host?.label ? <Check size={15} /> : '2'}</span><div><strong>Choose a topic</strong><small>{host?.label || topic || 'Add what you’re studying today'}</small></div><button className="text-button" onClick={onEditTopic}>Edit <ArrowUpRight size={14} /></button></div>
        {host && <div className="host-step"><span>3</span><div><strong>{host.muted ? 'Requests muted' : 'Taking requests'}</strong><small>{state === 'confirm_pending' ? 'Confirm you’re still here' : 'Mute anytime'}</small></div>{state === 'confirm_pending' ? <button className="text-button" onClick={onConfirm}>Confirm <Check size={14} /></button> : <button className="text-button" onClick={() => onMute(!host.muted)}>{host.muted ? 'Unmute' : 'Mute'}</button>}</div>}
      </div>}
    </div></main>
}

function InboxView({ inbox, hosting, onAnswer }) { return <main className="simple-page inbox-page"><div className="page-topline"><div><span className="eyebrow">Inbox</span><h1>People looking for a table.</h1></div><span className="count-badge">{inbox.length} pending</span></div><p className="lede">You’ll see their course and table only. Names appear after you accept.</p>{inbox.length ? <div className="request-list">{inbox.map((request) => <article className="request-card" key={request.request_id}><div className="request-avatar">?</div><div className="request-content"><span className="request-time"><Clock3 size={13} /> {request.seconds_left}s left</span><h2>Someone studying {request.course_label}</h2><p>Wants to join you at {request.table_label}.</p><div className="request-actions"><button className="primary-button small" onClick={() => onAnswer(request.request_id, 'accept')}><Check size={14} /> Accept</button><button className="quiet-button" onClick={() => onAnswer(request.request_id, 'decline')}>Not now</button><button className="icon-button" aria-label="Decline and mute requests" title="Decline and mute" onClick={() => onAnswer(request.request_id, 'mute')}><Bell size={15} /></button></div></div></article>)}</div> : <div className="empty-state"><MessageCircle size={25} /><strong>No requests right now.</strong><span>{hosting ? 'Keep this tab open while you study.' : 'Turn on host mode to receive requests.'}</span></div>}</main> }

const matchEndText = { completed: 'You’re all set. Enjoy studying!', cancelled: 'This match was cancelled.', expired: 'This match expired.' }

function MatchView({ match, onBack, onAction }) {
  if (!match) return <main className="match-page"><p className="lede">Loading your match…</p></main>
  const seat = match.alt_seat_id || match.assigned_seat_id
  const active = match.status === 'active'
  return <main className="match-page"><button className="back-button" onClick={onBack}>← Back to map</button><div className="match-intro"><span className="eyebrow"><span className="live-dot" /> {active ? 'You found a match' : 'Match ended'}</span><h1>Make the first hello<br /><em>feel easy.</em></h1><p>{active ? `Your table is waiting at ${match.building}.` : matchEndText[match.status]}</p></div>
    <div className="match-card"><div className="match-card-head"><span className="match-spark"><Sparkles size={18} /></span><span>Ghost Seats introduction</span><span className="match-time">{match.role === 'host' ? 'They’re coming to you' : 'You’re heading over'}</span></div>
      <div className="match-person"><div className="large-avatar">{match.other_first_name[0]}</div><div><span>Say hello to</span><h2>{match.other_first_name}</h2></div></div>
      <div className="match-details"><div><MapPin size={16} /><span><small>{match.alt_seat_id ? 'Your seat was taken; meet at' : 'Meet at'}</small><strong>{match.building} · Floor {match.floor} · {match.table_label}{seat ? ` · Seat ${seat}` : ''}</strong></span></div><div><MessageCircle size={16} /><span><small>Try this opener</small><strong>{match.icebreaker}</strong></span></div></div>
      {active && <div className="match-actions">{match.role === 'seeker' && <button className="primary-button" onClick={() => onAction('arrived')}><Check size={16} /> I’m here</button>}<button className="quiet-button" onClick={() => onAction('cancel')}>Cancel match</button></div>}
    </div></main>
}

function Modal({ title, onClose, children }) { return <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal"><button className="modal-close icon-button" onClick={onClose} aria-label="Close"><X size={18} /></button><span className="eyebrow">Ghost Seats</span><h2>{title}</h2>{children}</div></div> }

export default App

createRoot(document.getElementById('root')).render(<App />)
