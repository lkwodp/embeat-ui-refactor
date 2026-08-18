import { useEffect, useRef, useState } from 'react'
import { fetchHealth } from '../api/client'
import { ThemePicker } from './ThemePicker'
import { useAuth } from '../auth/AuthProvider'

export function formatNumber(value: number | string): string {
  return new Intl.NumberFormat('zh-CN').format(Number(value))
}

export function ServiceStatus({ poll = true }: { poll?: boolean }) {
  const [state, setState] = useState<'connecting' | 'online' | 'offline' | 'initializing'>('connecting')
  const [title, setTitle] = useState('正在连接')
  const [detail, setDetail] = useState('Qdrant')

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const health = await fetchHealth()
        if (cancelled) return
        if (!health.ready) {
          setState('initializing')
          setTitle('数据库初始化中')
          setDetail('首次启动约需一分钟')
          return
        }
        setState('online')
        setTitle('数据库在线')
        setDetail(`${formatNumber(health.points)} 首歌曲`)
      } catch {
        if (cancelled) return
        setState('offline')
        setTitle('数据库离线')
        setDetail('检查 Qdrant')
      }
    }
    void check()
    if (!poll) return () => { cancelled = true }
    const timer = window.setInterval(() => void check(), 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [poll])

  const className = state === 'online' ? 'service-status online' : state === 'offline' ? 'service-status offline' : state === 'initializing' ? 'service-status' : 'service-status'
  return (
    <div className={className} id="service-status">
      <span className="status-dot"></span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  )
}

export function AccountBadge() {
  const { user, authEnabled, logout } = useAuth()
  if (!authEnabled || !user) return null
  return (
    <div className="auth-account" id="auth-account">
      <span>{user.username}</span>
      <button type="button" onClick={() => void logout()}>
        退出
      </button>
    </div>
  )
}

interface BrandRowProps {
  tagline?: string
}

export function BrandRow({ tagline = 'Music Discovery' }: BrandRowProps) {
  return (
    <div className="brand-row">
      <a className="brand" href="/">
        <img className="brand-mark" src="/logo.svg" alt="Embeat logo" width="38" height="38" />
        <div>
          <strong>Embeat</strong>
          <small>{tagline}</small>
        </div>
      </a>
      <ThemePicker />
    </div>
  )
}

export function useToast() {
  const [message, setMessage] = useState('')
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<number | undefined>(undefined)

  function showToast(text: string) {
    window.clearTimeout(timerRef.current)
    setMessage(text)
    setVisible(true)
    timerRef.current = window.setTimeout(() => setVisible(false), 5000)
  }

  return { showToast, Toast: <div className={`toast ${visible ? '' : 'hidden'}`} role="alert">{message}</div> }
}