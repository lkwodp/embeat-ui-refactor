import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

export const THEMES = [
  { id: 'auto', name: '跟随系统', group: 'auto', colors: ['#f3f2ee', '#15191d'], hue: 8 },
  { id: 'studio', name: '录音室浅色', group: 'light', colors: ['#202124', '#e84b35'], hue: 8 },
  { id: 'ocean', name: '海洋渐变', group: 'light', colors: ['#18363e', '#147d8f'], hue: 188 },
  { id: 'forest', name: '林间唱片', group: 'light', colors: ['#24382f', '#d6533c'], hue: 8 },
  { id: 'graphite', name: '石墨工作室', group: 'light', colors: ['#303438', '#3477b5'], hue: 210 },
  { id: 'solar', name: '日光浸染', group: 'light', colors: ['#20292b', '#d79a22'], hue: 40 },
  { id: 'night', name: '深夜黑胶', group: 'dark', colors: ['#0d1013', '#ff6d58'], hue: 8 },
  { id: 'berry', name: '莓果夜色', group: 'dark', colors: ['#211e22', '#df5d7c'], hue: 345 },
  { id: 'contrast', name: '高对比', group: 'contrast', colors: ['#000000', '#b00020'], hue: 349 },
]

export const THEME_GROUPS = [
  { id: 'auto', name: '自动' },
  { id: 'light', name: '浅色' },
  { id: 'dark', name: '深色' },
  { id: 'contrast', name: '高对比' },
]

const STORAGE_KEY = 'embeat_ui_theme_v1'
const ACCENT_KEY = 'embeat_ui_accent_hue_v1'

const THEME_IDS = new Set(THEMES.map((theme) => theme.id))

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, String(value))
  } catch {
    /* Storage may be disabled. */
  }
}

function normalizeTheme(value: string | null | undefined): string {
  const normalized = String(value || '').toLowerCase()
  return THEME_IDS.has(normalized) ? normalized : 'auto'
}

function normalizeHue(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number.parseInt(String(value), 10)
  return Number.isFinite(parsed) ? Math.max(0, Math.min(359, parsed)) : null
}

export function isDarkTheme(themeId: string): boolean {
  return (
    themeId === 'night' ||
    themeId === 'berry' ||
    (themeId === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  )
}

const ACCENT_VARS = ['--accent', '--accent-hover', '--accent-dark', '--focus-ring', '--accent-ring', '--record-label'] as const

function clearAccentStyles(): void {
  const root = document.documentElement
  ACCENT_VARS.forEach((name) => root.style.removeProperty(name))
  delete root.dataset.customAccent
}

function applyAccentStyles(hue: number | null): void {
  clearAccentStyles()
  if (hue === null) return
  const root = document.documentElement
  const dark = isDarkTheme(root.dataset.theme || 'auto')
  const accentLightness = dark ? 66 : 43
  const hoverLightness = dark ? 72 : 49
  const darkLightness = dark ? 82 : 34
  const focusLightness = dark ? 78 : 32
  root.style.setProperty('--accent', `hsl(${hue} 72% ${accentLightness}%)`)
  root.style.setProperty('--accent-hover', `hsl(${hue} 76% ${hoverLightness}%)`)
  root.style.setProperty('--accent-dark', `hsl(${hue} 68% ${darkLightness}%)`)
  root.style.setProperty('--focus-ring', `hsl(${hue} 82% ${focusLightness}%)`)
  root.style.setProperty('--accent-ring', `hsl(${hue} 76% 50% / 22%)`)
  root.style.setProperty('--record-label', 'var(--accent)')
  root.dataset.customAccent = 'true'
}

interface ThemeContextValue {
  theme: string
  accentHue: number | null
  setTheme: (themeId: string, options?: { account?: boolean; local?: boolean }) => void
  setAccent: (hue: number | null, options?: { account?: boolean; local?: boolean }) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

async function postPreference(payload: Record<string, unknown>): Promise<void> {
  try {
    await fetch('/api/preferences', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    /* Local preference remains available when the server is offline. */
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<string>(() =>
    normalizeTheme(readStorage(STORAGE_KEY)),
  )
  const [accentHue, setAccentHueState] = useState<number | null>(() =>
    normalizeHue(readStorage(ACCENT_KEY)),
  )
  const pendingRef = useRef<Record<string, unknown>>({})
  const timerRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    applyAccentStyles(accentHue)
  }, [theme, accentHue])

  const queuePreferenceSave = useCallback((patch: Record<string, unknown>) => {
    pendingRef.current = { ...pendingRef.current, ...patch }
    window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      const payload = pendingRef.current
      pendingRef.current = {}
      void postPreference(payload)
    }, 180)
  }, [])

  const setTheme = useCallback(
    (themeId: string, options: { account?: boolean; local?: boolean } = {}) => {
      const normalized = normalizeTheme(themeId)
      setThemeState(normalized)
      if (options.local !== false) writeStorage(STORAGE_KEY, normalized)
      if (options.account) queuePreferenceSave({ theme: normalized })
    },
    [queuePreferenceSave],
  )

  const setAccent = useCallback(
    (hue: number | null, options: { account?: boolean; local?: boolean } = {}) => {
      const normalized = normalizeHue(hue)
      setAccentHueState(normalized)
      if (options.local !== false) writeStorage(ACCENT_KEY, normalized === null ? '' : String(normalized))
      if (options.account) queuePreferenceSave({ accent_hue: normalized })
    },
    [queuePreferenceSave],
  )

  // Load account preferences once the auth gate resolves.
  useEffect(() => {
    const onReady = async () => {
      try {
        const response = await fetch('/api/preferences', { credentials: 'same-origin' })
        if (!response.ok) return
        const preferences = (await response.json()) as { theme?: string; accent_hue?: number | null }
        if (preferences.theme && THEME_IDS.has(preferences.theme)) setTheme(preferences.theme)
        if (preferences.accent_hue !== null && preferences.accent_hue !== undefined) {
          setAccent(preferences.accent_hue)
        }
      } catch {
        /* Browser-local preferences remain active. */
      }
    }
    window.addEventListener('embeat-authenticated', onReady)
    if (window.embeatAuthReady) {
      window.embeatAuthReady.then(() => onReady())
    }
    return () => window.removeEventListener('embeat-authenticated', onReady)
  }, [setTheme, setAccent])

  // Sync across tabs.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setTheme(normalizeTheme(event.newValue || 'auto'))
      if (event.key === ACCENT_KEY) setAccent(normalizeHue(event.newValue))
    }
    const onSchemeChange = () => {
      if (theme === 'auto') applyAccentStyles(accentHue)
    }
    window.addEventListener('storage', onStorage)
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', onSchemeChange)
    return () => {
      window.removeEventListener('storage', onStorage)
      media.removeEventListener('change', onSchemeChange)
    }
  }, [theme, accentHue, setTheme, setAccent])

  const value = useMemo(
    () => ({ theme, accentHue, setTheme, setAccent }),
    [theme, accentHue, setTheme, setAccent],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within a ThemeProvider')
  return context
}
