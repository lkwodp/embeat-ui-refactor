import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from './AuthProvider'

export function AuthGate() {
  const { authEnabled, gateVisible, login, register, pair } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!gateVisible) return null

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setSubmitting(true)
    setError('')
    try {
      if (authEnabled) {
        const username = String(data.get('username') || '')
        const password = String(data.get('password') || '')
        if (mode === 'register') {
          await register(username, password, String(data.get('invite_code') || ''))
        } else {
          await login(username, password)
        }
      } else {
        await pair(String(data.get('pair_code') || ''))
      }
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div id="auth-gate" className="auth-gate">
      {authEnabled ? (
        <div className="auth-card">
          <div className="auth-brand">
            <img src="/logo.svg" width="42" height="42" alt="" />
            <div>
              <strong>Embeat</strong>
              <small>私人音乐推荐空间</small>
            </div>
          </div>
          <div className="auth-tabs">
            <button type="button" data-auth-mode="login" className={mode === 'login' ? 'active' : ''} onClick={() => { setMode('login'); setError('') }}>
              登录
            </button>
            <button type="button" data-auth-mode="register" className={mode === 'register' ? 'active' : ''} onClick={() => { setMode('register'); setError('') }}>
              注册
            </button>
          </div>
          <form id="auth-form" onSubmit={handleSubmit}>
            <label>
              用户名
              <input name="username" autoComplete="username" required maxLength={80} />
            </label>
            <label>
              密码
              <input name="password" type="password" autoComplete={mode === 'register' ? 'new-password' : 'current-password'} required minLength={8} />
            </label>
            {mode === 'register' ? (
              <label>
                邀请码
                <input name="invite_code" autoComplete="off" />
              </label>
            ) : null}
            <p className="auth-error" role="alert">
              {error}
            </p>
            <button className="primary-button" type="submit" disabled={submitting}>
              {mode === 'register' ? '注册并登录' : '登录'}
            </button>
          </form>
        </div>
      ) : (
        <div className="auth-card">
          <div className="auth-brand">
            <img src="/logo.svg" width="42" height="42" alt="" />
            <div>
              <strong>Embeat</strong>
              <small>私人音乐推荐空间</small>
            </div>
          </div>
          <p className="auth-error" style={{ color: 'var(--muted)' }}>
            本服务未开启账号登录，请输入服务器启动时显示的配对码。
          </p>
          <form id="auth-form" onSubmit={handleSubmit}>
            <label>
              配对码
              <input name="pair_code" autoComplete="off" required />
            </label>
            <p className="auth-error" role="alert">
              {error}
            </p>
            <button className="primary-button" type="submit" disabled={submitting}>
              配对
            </button>
          </form>
        </div>
      )}
    </div>
  )
}