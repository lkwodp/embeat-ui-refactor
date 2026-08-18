import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchHealth } from '../api/client'
import { ThemePicker } from './ThemePicker'
import { useAuth } from '../auth/AuthProvider'

export function formatNumber(value: number | string): string {
  return new Intl.NumberFormat('zh-CN').format(Number(value))
}

export function BackButton({ onClick, fallbackTo = '/' }: { onClick?: () => void; fallbackTo?: string }) {
  const navigate = useNavigate()
  const handleBack = () => {
    if (onClick) return onClick()
    if (window.history.length > 1) {
      window.history.back()
    } else {
      navigate(fallbackTo)
    }
  }
  return (
    <button type="button" className="back-button" title="返回上一页" aria-label="返回上一页" onClick={handleBack}>
      <svg viewBox="0 0 1024 1024" width="16" height="16" aria-hidden="true">
        <path d="M137.195012 473.012753l343.015525-236.983218-0.308863 468.654345z" />
        <path d="M480.667511 706.240841l-1.146949-0.774868L135.66695 473.021784 480.978181 234.452705v1.578636l-0.31067 470.2095zM138.723073 473.003722L479.135837 703.125112l0.308863-465.518748L138.723073 473.003722z" />
        <path d="M807.983377 647.341831s-7.347701-39.173288-31.538398-63.073184c-18.555293-18.331321-30.10426-28.670122-57.340243-34.404868-70.879664-14.921179-394.378989 0.050574-394.378989 0.050574V413.73263s214.893154-3.375824 285.431443 11.417113c20.932277 4.389113 57.967001 10.044386 83.143895 22.935375 27.143866 13.900665 53.628462 34.040012 67.375598 50.173164 46.838883 54.974096 47.306694 149.083548 47.306694 149.083549z" />
      </svg>
    </button>
  )
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