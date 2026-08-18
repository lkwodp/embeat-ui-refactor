import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { fetchAuthMe, logout, pairDevice, login as apiLogin, register as apiRegister } from '../api/client'
import type { AuthMeResponse } from '../types'

export interface AuthUser {
  id: number
  username: string
}

interface AuthContextValue {
  user: AuthUser | null
  authEnabled: boolean
  ready: boolean
  gateVisible: boolean
  showGate: () => void
  hideGate: () => void
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, inviteCode?: string) => Promise<void>
  pair: (code: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

declare global {
  interface Window {
    embeatAuthReady: Promise<unknown> | undefined
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [authEnabled, setAuthEnabled] = useState(true)
  const [ready, setReady] = useState(false)
  const [gateVisible, setGateVisible] = useState(false)
  const resolverRef = useRef<((value: unknown) => void) | undefined>(undefined)

  const readyPromise = useMemo(() => {
    return new Promise((resolve) => {
      resolverRef.current = resolve
    })
  }, [])

  useEffect(() => {
    window.embeatAuthReady = readyPromise
    return () => {
      window.embeatAuthReady = undefined
    }
  }, [readyPromise])

  const resolve = useCallback(() => {
    if (resolverRef.current) {
      resolverRef.current(user)
      resolverRef.current = undefined
    }
  }, [user])

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const data = await fetchAuthMe()
        if (cancelled) return
        setAuthEnabled(data.auth_enabled !== false)
        setUser(data.user)
        setReady(true)
        resolve()
      } catch {
        if (cancelled) return
        setGateVisible(true)
        setReady(true)
      }
    }
    void check()
    return () => {
      cancelled = true
    }
  }, [resolve])

  useEffect(() => {
    const onAuthRequired = () => setGateVisible(true)
    const onAuthenticated = () => setGateVisible(false)
    window.addEventListener('embeat-auth-required', onAuthRequired)
    window.addEventListener('embeat-authenticated', onAuthenticated)
    return () => {
      window.removeEventListener('embeat-auth-required', onAuthRequired)
      window.removeEventListener('embeat-authenticated', onAuthenticated)
    }
  }, [])

  const complete = useCallback(
    (data: AuthMeResponse) => {
      setAuthEnabled(data.auth_enabled !== false)
      setUser(data.user)
      setGateVisible(false)
      window.dispatchEvent(new CustomEvent('embeat-authenticated', { detail: data.user }))
      resolve()
    },
    [resolve],
  )

  const login = useCallback(
    async (username: string, password: string) => {
      complete(await apiLogin(username, password))
    },
    [complete],
  )

  const register = useCallback(
    async (username: string, password: string, inviteCode = '') => {
      complete(await apiRegister(username, password, inviteCode))
    },
    [complete],
  )

  const pair = useCallback(
    async (code: string) => {
      complete(await pairDevice(code))
    },
    [complete],
  )

  const doLogout = useCallback(async () => {
    await logout()
    window.location.reload()
  }, [])

  const value = useMemo(
    () => ({
      user,
      authEnabled,
      ready,
      gateVisible,
      showGate: () => setGateVisible(true),
      hideGate: () => setGateVisible(false),
      login,
      register,
      pair,
      logout: doLogout,
    }),
    [user, authEnabled, ready, gateVisible, login, register, pair, doLogout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}