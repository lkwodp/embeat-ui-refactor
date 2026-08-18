import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

function applyInitialTheme() {
  try {
    const value = localStorage.getItem('embeat_ui_theme_v1')
    const valid = ['auto', 'studio', 'night', 'ocean', 'contrast', 'forest', 'berry', 'graphite', 'solar']
    document.documentElement.dataset.theme = valid.includes(value || '') ? value! : 'auto'
  } catch {
    document.documentElement.dataset.theme = 'auto'
  }
}

applyInitialTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)