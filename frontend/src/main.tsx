import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import './design/tokens.css'
import './design/base.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './app/App'

// A deploy replaces the hashed chunks; an old page that asks for one reloads once to pick up the new build.
window.addEventListener('vite:preloadError', () => {
  if (sessionStorage.getItem('gs-reloaded') === null) {
    sessionStorage.setItem('gs-reloaded', '1')
    window.location.reload()
  }
})

const root = document.getElementById('root')
if (!root) throw new Error('missing #root')
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
