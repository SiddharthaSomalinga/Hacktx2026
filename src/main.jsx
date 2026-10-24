import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import {
  ArrowUpRight,
  BookOpen,
  ChevronDown,
  CircleHelp,
  Clock3,
  Coffee,
  Compass,
  HeartHandshake,
  MapPin,
  Menu,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import './styles.css'

const buildings = [
  { id: 'pcl', name: 'PCL Library', short: 'PCL', floor: '2nd floor', seats: 148, open: 62, likely: 19, accent: 'sage', note: 'Best availability' },
  { id: 'wel', name: 'WEL Library', short: 'WEL', floor: '1st floor', seats: 96, open: 21, likely: 14, accent: 'coral', note: 'Filling up' },
  { id: 'gdc', name: 'GDC Study Hall', short: 'GDC', floor: '3rd floor', seats: 74, open: 46, likely: 8, accent: 'gold', note: 'Simulated', simulated: true },
]

const initialSeats = [
  { id: 'a1', number: 'A1', status: 'open', x: 13, y: 22 },
  { id: 'a2', number: 'A2', status: 'occupied', x: 25, y: 22 },
  { id: 'a3', number: 'A3', status: 'likely', x: 37, y: 22 },
  { id: 'a4', number: 'A4', status: 'open', x: 49, y: 22 },
  { id: 'a5', number: 'A5', status: 'open', x: 61, y: 22 },
  { id: 'a6', number: 'A6', status: 'offline', x: 73, y: 22 },
  { id: 'b1', number: 'B1', status: 'occupied', x: 13, y: 57 },
  { id: 'b2', number: 'B2', status: 'open', x: 25, y: 57 },
  { id: 'b3', number: 'B3', status: 'open', x: 37, y: 57 },
  { id: 'b4', number: 'B4', status: 'likely', x: 49, y: 57 },
  { id: 'b5', number: 'B5', status: 'open', x: 61, y: 57 },
  { id: 'b6', number: 'B6', status: 'occupied', x: 73, y: 57 },
]

const statusMeta = {
  open: { label: 'Open', className: 'open' },
  occupied: { label: 'Occupied', className: 'occupied' },
  likely: { label: 'Likely opening', className: 'likely' },
  offline: { label: 'Offline', className: 'offline' },
}

function App() {
  const [selectedBuilding, setSelectedBuilding] = useState('pcl')
  const [seats, setSeats] = useState(initialSeats)
  const [topic, setTopic] = useState('')
  const [normalizedTopic, setNormalizedTopic] = useState('')
  const [isHost, setIsHost] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [toast, setToast] = useState('')
  const [selectedSeat, setSelectedSeat] = useState('a1')

  const building = buildings.find((item) => item.id === selectedBuilding) ?? buildings[0]

  useEffect(() => {
    const timer = setInterval(() => {
      setSeats((current) => current.map((seat, index) => {
        if (index !== 0 && index !== 3) return seat
        return { ...seat, status: seat.status === 'open' ? 'likely' : 'open' }
      }))
    }, 9000)
    return () => clearInterval(timer)
  }, [])

  function announce(message) {
    setToast(message)
    window.setTimeout(() => setToast(''), 3600)
  }

  function handleTopicSubmit(event) {
    event.preventDefault()
    if (!topic.trim()) return
    setNormalizedTopic(topic.toLowerCase().includes('320') || topic.toLowerCase().includes('orgo')
      ? 'CH 320M · Organic Chemistry I'
      : `${topic.trim()} · Topic match ready`)
    announce('Topic normalized. 7 compatible study partners nearby.')
  }

  function handleBuildingChange(id) {
    setSelectedBuilding(id)
    setSelectedSeat('a1')
    announce(`Showing ${buildings.find((item) => item.id === id)?.name}`)
  }

  function requestMatch() {
    announce('Request sent. We’ll let you know when they accept.')
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Ghost Seats home">
          <span className="brand-mark"><span /></span>
          <span>ghost <strong>seats</strong></span>
        </a>
        <nav className="desktop-nav" aria-label="Main navigation">
          <a className="active" href="#map">Find a seat</a>
          <a href="#matches">Study matches <span className="nav-dot" /></a>
          <a href="#about">How it works</a>
        </nav>
        <div className="top-actions">
          <button className="icon-button help-button" aria-label="Help"><CircleHelp size={18} /></button>
          <button className="user-button" onClick={() => announce('Demo login picker coming next.')}>Siddhartha <ChevronDown size={15} /></button>
          <button className="icon-button menu-button" aria-label="Open menu" onClick={() => setShowMenu(!showMenu)}><Menu size={19} /></button>
        </div>
        {showMenu && <div className="mobile-menu"><a href="#map">Find a seat</a><a href="#matches">Study matches</a><a href="#about">How it works</a></div>}
      </header>

      <main id="top">
        <section className="intro-band">
          <div className="intro-copy">
            <div className="eyebrow"><span className="live-pip" /> Live across UT Austin</div>
            <h1>Find a seat.<br /><em>Find your people.</em></h1>
            <p>See what’s actually open, then find someone studying the same thing. No wandering. No awkward cold starts.</p>
          </div>
          <form className="topic-card" onSubmit={handleTopicSubmit}>
            <div className="topic-card-heading"><Sparkles size={18} /><span>What are you studying today?</span><span className="optional">Optional</span></div>
            <div className="topic-input-wrap">
              <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="Try “orgo 1 exam prep”" aria-label="What are you studying today" />
              <button aria-label="Search for study matches" type="submit"><ArrowUpRight size={19} /></button>
            </div>
            {normalizedTopic ? <div className="normalized"><span>✦</span> {normalizedTopic}</div> : <div className="topic-hint">Skip for now <span>→</span></div>}
          </form>
        </section>

        <section className="workspace" id="map">
          <aside className="building-sidebar">
            <div className="section-kicker">Nearby buildings <span>Updated just now</span></div>
            <div className="building-list">
              {buildings.map((item) => (
                <button className={`building-item ${selectedBuilding === item.id ? 'selected' : ''}`} key={item.id} onClick={() => handleBuildingChange(item.id)}>
                  <span className={`building-icon ${item.accent}`}>{item.short.slice(0, 1)}</span>
                  <span className="building-info"><strong>{item.name}</strong><small>{item.floor} {item.simulated && <span className="simulated-tag">Simulated</span>}</small></span>
                  <span className="building-count"><strong>{item.open}</strong><small>open</small></span>
                </button>
              ))}
            </div>
            <div className="side-rule" />
            <div className="availability-note"><div className="note-icon"><Compass size={17} /></div><div><strong>Want the best shot?</strong><p>Try <b>GDC Study Hall</b> — 62% of seats are open right now.</p></div></div>
            <button className="outline-button" onClick={() => announce('All buildings are available in the full map view.')}>View all buildings <ArrowUpRight size={16} /></button>
          </aside>

          <section className="map-panel">
            <div className="map-heading"><div><div className="section-kicker">Seat map</div><h2>{building.name} <span className="live-status"><span /> Live</span></h2><p>{building.floor} · <span className="simulated-copy">{building.simulated ? 'Simulated building' : 'Occupancy from seat nodes'}</span></p></div><button className="floor-select">Floor 2 <ChevronDown size={15} /></button></div>
            <div className="map-canvas" aria-label={`${building.name} seat map`}>
              <div className="map-label label-north">Windows</div><div className="map-label label-south">Quiet zone</div><div className="map-door door-one">ENTRY</div><div className="map-door door-two">STAIRS</div>
              <div className="table-shape table-one"><span>Table 01</span></div><div className="table-shape table-two"><span>Table 02</span></div>
              {seats.map((seat) => <button key={seat.id} className={`seat-marker ${statusMeta[seat.status].className} ${selectedSeat === seat.id ? 'selected' : ''}`} style={{ left: `${seat.x}%`, top: `${seat.y}%` }} onClick={() => setSelectedSeat(seat.id)} aria-label={`${seat.number}: ${statusMeta[seat.status].label}`}><span>{seat.number}</span></button>)}
              <div className="map-pin"><MapPin size={14} fill="currentColor" /><span>You are here</span></div>
            </div>
            <div className="map-footer"><div className="legend"><span><i className="legend-dot open" /> Open <b>{building.open}</b></span><span><i className="legend-dot likely" /> Likely opening <b>{building.likely}</b></span><span><i className="legend-dot occupied" /> Occupied</span><span><i className="legend-dot offline" /> Offline</span></div><span className="refresh-label"><Clock3 size={14} /> Refreshes every 3 sec</span></div>
          </section>
        </section>

        <section className="lower-grid" id="matches">
          <div className="recommendation-panel">
            <div className="section-kicker">Recommended for you</div><h2>There’s room at the table.</h2><p>Seat <b>A1</b> at PCL is open now, with two compatible study sessions nearby.</p>
            <div className="recommendation-seat"><div className="seat-illustration"><span>A1</span></div><div><strong>PCL · 2nd floor · Table 01</strong><small>Quiet corner · Power nearby</small></div><button onClick={() => { setSelectedSeat('a1'); announce('Seat A1 selected.') }} aria-label="Select recommended seat"><ArrowUpRight size={18} /></button></div>
          </div>
          <div className="host-panel"><div className="host-heading"><div className="host-icon"><Users size={19} /></div><div><div className="section-kicker">Host mode</div><h2>Open to studying together?</h2></div><button className={`toggle ${isHost ? 'on' : ''}`} onClick={() => { setIsHost(!isHost); announce(isHost ? 'Host mode turned off.' : 'Host mode is on. You are discoverable.') }} aria-label="Toggle host mode"><span /></button></div><p>Let nearby students know you’re open to a low-key study partner. You stay in control.</p><div className="host-footer"><span><ShieldCheck size={15} /> Names stay private until you accept</span><button onClick={() => setIsHost(!isHost)}>{isHost ? 'Turn off host mode' : 'Turn on host mode'} <ArrowUpRight size={15} /></button></div></div>
        </section>

        <section className="match-strip" id="about"><div className="match-strip-copy"><span className="match-kicker"><HeartHandshake size={16} /> Built for the study break</span><h2>Same library. Same class.<br /><em>Maybe the same problem set.</em></h2><p>Ghost Seats pairs open seats with real study intent, so finding a person to work with feels as easy as finding a place to sit.</p></div><div className="match-preview"><div className="preview-header"><span className="avatar avatar-coral">M</span><div><strong>Organic Chemistry I</strong><small>Table 01 · 2 min away</small></div><span className="match-score">94% match</span></div><div className="preview-quote">“Comparing R/S configurations on Problem 4?”</div><button className="preview-action" onClick={requestMatch}>Request to study <ArrowUpRight size={16} /></button></div></section>
      </main>

      <footer><span>ghost seats / UT Austin</span><span>Privacy first · No images or audio stored</span><span>Built for the library regulars</span></footer>
      {toast && <div className="toast"><Sparkles size={16} /> {toast}<button onClick={() => setToast('')} aria-label="Dismiss notification"><X size={14} /></button></div>}
    </div>
  )
}

export default App

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
