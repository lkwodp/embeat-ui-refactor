import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './theme/ThemeProvider'
import { AuthProvider } from './auth/AuthProvider'
import { AuthGate } from './auth/AuthGate'
import { Home } from './pages/Home'
import { Radio } from './pages/Radio'
import { Settings } from './pages/Settings'
import './styles/app.css'

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/radio" element={<Radio />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </BrowserRouter>
        <AuthGate />
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App