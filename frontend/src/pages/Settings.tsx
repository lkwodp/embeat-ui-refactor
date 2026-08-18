import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { fetchConfig, fetchHealth, loginCaptcha, savePlatformConfig, sendCaptcha } from '../api/client'
import { AccountBadge, BackButton, BrandRow, useToast } from '../components/common'

const platformNames: Record<string, string> = { netease: '网易云音乐', kugou: '酷狗音乐' }

function maskPhone(phone: string): string {
  return phone.length >= 7 ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone
}

interface PanelState {
  api: string
  proxy: string
  cookie: string
  phone: string
  code: string
  country: string
  state: string
  stateStatus: 'loading' | 'online' | 'offline' | ''
  sendLabel: string
  sendDisabled: boolean
  saveBusy: boolean
  loginBusy: boolean
}

function initialPanel(country: string): PanelState {
  return {
    api: '',
    proxy: '',
    cookie: '',
    phone: '',
    code: '',
    country,
    state: '未连接',
    stateStatus: '',
    sendLabel: '发送验证码',
    sendDisabled: false,
    saveBusy: false,
    loginBusy: false,
  }
}

export function Settings() {
  const { showToast, Toast } = useToast()
  const [netease, setNetease] = useState<PanelState>(() => initialPanel('86'))
  const [kugou, setKugou] = useState<PanelState>(() => initialPanel('86'))
  const [serviceTitle, setServiceTitle] = useState('正在连接')
  const [serviceDetail, setServiceDetail] = useState('Embeat')
  const [serviceOnline, setServiceOnline] = useState(false)
  const [serviceOffline, setServiceOffline] = useState(false)

  useEffect(() => {
    void checkHealth()
    void loadDefaults()
    void loadStatus('netease')
    void loadStatus('kugou')
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function checkHealth() {
    try {
      const health = await fetchHealth()
      setServiceOnline(health.ready)
      setServiceOffline(!health.ready)
      setServiceTitle(health.ready ? '服务在线' : '数据库初始化中')
      setServiceDetail(health.ready ? `${new Intl.NumberFormat('zh-CN').format(health.points)} 首歌曲` : '请稍候')
    } catch {
      setServiceOffline(true)
      setServiceOnline(false)
      setServiceTitle('服务离线')
    }
  }

  async function loadDefaults() {
    try {
      const defaults = await fetchConfig()
      setNetease((prev) => ({ ...prev, api: prev.api || defaults.netease_api_url || '' }))
      setKugou((prev) => ({ ...prev, api: prev.api || defaults.kugou_api_url || '' }))
      const proxy = defaults.proxy_url || ''
      setNetease((prev) => ({ ...prev, proxy: prev.proxy || proxy }))
      setKugou((prev) => ({ ...prev, proxy: prev.proxy || proxy }))
    } catch {
      /* 默认值不可用时不提示 */
    }
  }

  async function loadStatus(platform: 'netease' | 'kugou') {
    const setPanel = platform === 'netease' ? setNetease : setKugou
    setPanel((prev) => ({ ...prev, state: '检查中', stateStatus: 'loading' }))
    try {
      const response = await fetch(`/api/${platform}/config`, { credentials: 'same-origin' })
      const status = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(status.error || `请求失败 (${response.status})`)
      setPanel((prev) => ({
        ...prev,
        api: status.api_url || prev.api,
        proxy: status.proxy_url !== undefined ? status.proxy_url : prev.proxy,
        phone: status.phone || prev.phone,
        state: status.configured ? `已连接${status.uid || status.userid ? ` · UID ${status.uid || status.userid}` : ''}` : '未连接',
        stateStatus: status.configured ? 'online' : 'offline',
      }))
    } catch (error) {
      setPanel((prev) => ({ ...prev, state: '状态读取失败', stateStatus: 'offline' }))
      showToast((error as Error).message)
    }
  }

  function values(panel: PanelState): { api_url: string; proxy_url: string; cookie: string; phone: string; code: string; country_code: string } {
    return {
      api_url: panel.api.trim(),
      proxy_url: panel.proxy.trim(),
      cookie: panel.cookie.trim(),
      phone: panel.phone.trim(),
      code: panel.code.trim(),
      country_code: panel.country.trim() || '86',
    }
  }

  async function saveCookie(event: FormEvent<HTMLFormElement>, platform: 'netease' | 'kugou') {
    event.preventDefault()
    const setPanel = platform === 'netease' ? setNetease : setKugou
    const data = values(platform === 'netease' ? netease : kugou)
    if (!data.api_url || !data.cookie) return showToast('请填写 API 地址和 Cookie')
    setPanel((prev) => ({ ...prev, saveBusy: true }))
    try {
      await savePlatformConfig(platform, data)
      setPanel((prev) => ({ ...prev, cookie: '' }))
      showToast(`${platformNames[platform]}凭据已加密保存`)
      await loadStatus(platform)
    } catch (error) {
      showToast((error as Error).message)
    } finally {
      setPanel((prev) => ({ ...prev, saveBusy: false }))
    }
  }

  function countdown(_label: string, setPanel: React.Dispatch<React.SetStateAction<PanelState>>) {
    let remaining = 60
    setPanel((prev) => ({ ...prev, sendLabel: `${remaining}s`, sendDisabled: true }))
    const timer = window.setInterval(() => {
      remaining -= 1
      setPanel((prev) => ({
        ...prev,
        sendLabel: remaining > 0 ? `${remaining}s` : '发送验证码',
        sendDisabled: remaining <= 0 ? false : true,
      }))
      if (remaining <= 0) window.clearInterval(timer)
    }, 1000)
  }

  async function doSendCaptcha(platform: 'netease' | 'kugou') {
    const setPanel = platform === 'netease' ? setNetease : setKugou
    const panel = platform === 'netease' ? netease : kugou
    const data = values(panel)
    if (!data.api_url || !data.phone) return showToast('请填写 API 地址和手机号')
    setPanel((prev) => ({ ...prev, sendDisabled: true }))
    try {
      await sendCaptcha(platform, data)
      showToast(`验证码已发送至 ${maskPhone(data.phone)}`)
      countdown('发送验证码', setPanel)
    } catch (error) {
      setPanel((prev) => ({ ...prev, sendDisabled: false }))
      showToast((error as Error).message)
    }
  }

  async function loginByPhone(event: FormEvent<HTMLFormElement>, platform: 'netease' | 'kugou') {
    event.preventDefault()
    const setPanel = platform === 'netease' ? setNetease : setKugou
    const panel = platform === 'netease' ? netease : kugou
    const data = values(panel)
    if (!data.api_url || !data.phone || !data.code) return showToast('请填写手机号和验证码')
    setPanel((prev) => ({ ...prev, loginBusy: true }))
    try {
      await loginCaptcha(platform, data)
      setPanel((prev) => ({ ...prev, code: '' }))
      showToast(`${platformNames[platform]}登录成功，凭据已加密保存`)
      await loadStatus(platform)
    } catch (error) {
      showToast((error as Error).message)
    } finally {
      setPanel((prev) => ({ ...prev, loginBusy: false }))
    }
  }

  async function clearCredential(platform: 'netease' | 'kugou') {
    if (!window.confirm(`确定清除当前用户的${platformNames[platform]}凭据？`)) return
    try {
      await savePlatformConfig(platform, { clear: true })
      const setPanel = platform === 'netease' ? setNetease : setKugou
      setPanel((prev) => ({ ...prev, cookie: '' }))
      showToast('凭据已清除')
      await loadStatus(platform)
    } catch (error) {
      showToast((error as Error).message)
    }
  }

  const serviceClass = serviceOffline ? 'service-status offline' : serviceOnline ? 'service-status online' : 'service-status'

  return (
    <div className="app-shell settings-page">
      <aside className="sidebar settings-sidebar">
        <BrandRow tagline="Account Settings" />
        <nav className="radio-nav" aria-label="页面导航">
          <a href="/">歌曲推荐</a>
          <a href="/radio">歌单电台</a>
          <a className="active" href="/settings" aria-current="page">
            平台账号
          </a>
        </nav>
        <div className={serviceClass} id="settings-service-status">
          <span className="status-dot"></span>
          <div>
            <strong>{serviceTitle}</strong>
            <small>{serviceDetail}</small>
          </div>
        </div>
        <AccountBadge />
      </aside>

      <main className="workspace settings-workspace">
        <header className="topbar">
          <div className="topbar-heading">
            <BackButton />
            <div>
              <p className="eyebrow">Platform Accounts</p>
              <h1>平台账号配置</h1>
            </div>
          </div>
          <div className="topbar-meta">按当前 Embeat 用户隔离</div>
        </header>
        <div className="settings-grid">
          <section className="settings-platform" data-platform="netease">
            <div className="settings-platform-header">
              <div>
                <p className="eyebrow">NetEase Cloud Music</p>
                <h2>网易云音乐</h2>
              </div>
              <span className="settings-state" data-role="state" data-status={netease.stateStatus}>
                {netease.state}
              </span>
            </div>
            <div className="settings-fields">
              <label>
                兼容 API 地址
                <input data-role="api" className="light-input" placeholder="https://your-netease-api.example.com" autoComplete="off" value={netease.api} onChange={(event) => setNetease((prev) => ({ ...prev, api: event.target.value }))} />
              </label>
              <label>
                HTTP 代理
                <input data-role="proxy" className="light-input" placeholder="可留空" autoComplete="off" value={netease.proxy} onChange={(event) => setNetease((prev) => ({ ...prev, proxy: event.target.value }))} />
              </label>
            </div>
            <form className="settings-method" data-role="cookie-form" onSubmit={(event) => void saveCookie(event, 'netease')}>
              <div className="settings-method-title">
                <strong>Cookie 连接</strong>
                <small>保存后不再回显</small>
              </div>
              <label>
                Cookie
                <textarea data-role="cookie" className="light-input cookie-input" autoComplete="off" required value={netease.cookie} onChange={(event) => setNetease((prev) => ({ ...prev, cookie: event.target.value }))} />
              </label>
              <button className="primary-button" type="submit" disabled={netease.saveBusy}>
                {netease.saveBusy ? '正在校验' : '校验并保存'}
              </button>
            </form>
            <form className="settings-method" data-role="phone-form" onSubmit={(event) => void loginByPhone(event, 'netease')}>
              <div className="settings-method-title">
                <strong>手机验证码登录</strong>
                <small>中国大陆默认 +86</small>
              </div>
              <div className="settings-phone-row">
                <label>
                  区号
                  <input data-role="country" className="light-input" value={netease.country} inputMode="numeric" onChange={(event) => setNetease((prev) => ({ ...prev, country: event.target.value }))} />
                </label>
                <label>
                  手机号
                  <input data-role="phone" className="light-input" inputMode="tel" autoComplete="tel" required value={netease.phone} onChange={(event) => setNetease((prev) => ({ ...prev, phone: event.target.value }))} />
                </label>
                <button data-role="send" className="secondary-button" type="button" disabled={netease.sendDisabled} onClick={() => void doSendCaptcha('netease')}>
                  {netease.sendLabel}
                </button>
              </div>
              <div className="settings-code-row">
                <label>
                  验证码
                  <input data-role="code" className="light-input" inputMode="numeric" autoComplete="one-time-code" required value={netease.code} onChange={(event) => setNetease((prev) => ({ ...prev, code: event.target.value }))} />
                </label>
                <button className="primary-button" type="submit" disabled={netease.loginBusy}>
                  {netease.loginBusy ? '正在登录' : '登录并保存'}
                </button>
              </div>
            </form>
            <button className="forget-button" data-role="clear" type="button" onClick={() => void clearCredential('netease')}>
              清除网易云凭据
            </button>
          </section>

          <section className="settings-platform" data-platform="kugou">
            <div className="settings-platform-header">
              <div>
                <p className="eyebrow">KuGou Music</p>
                <h2>酷狗音乐</h2>
              </div>
              <span className="settings-state" data-role="state" data-status={kugou.stateStatus}>
                {kugou.state}
              </span>
            </div>
            <div className="settings-fields">
              <label>
                兼容 API 地址
                <input data-role="api" className="light-input" placeholder="https://your-kugou-api.example.com" autoComplete="off" value={kugou.api} onChange={(event) => setKugou((prev) => ({ ...prev, api: event.target.value }))} />
              </label>
              <label>
                HTTP 代理
                <input data-role="proxy" className="light-input" placeholder="可留空" autoComplete="off" value={kugou.proxy} onChange={(event) => setKugou((prev) => ({ ...prev, proxy: event.target.value }))} />
              </label>
            </div>
            <form className="settings-method" data-role="cookie-form" onSubmit={(event) => void saveCookie(event, 'kugou')}>
              <div className="settings-method-title">
                <strong>Cookie 连接</strong>
                <small>需包含 token 与 userid</small>
              </div>
              <label>
                Cookie
                <textarea data-role="cookie" className="light-input cookie-input" autoComplete="off" required value={kugou.cookie} onChange={(event) => setKugou((prev) => ({ ...prev, cookie: event.target.value }))} />
              </label>
              <button className="primary-button" type="submit" disabled={kugou.saveBusy}>
                {kugou.saveBusy ? '正在校验' : '校验并保存'}
              </button>
            </form>
            <form className="settings-method" data-role="phone-form" onSubmit={(event) => void loginByPhone(event, 'kugou')}>
              <div className="settings-method-title">
                <strong>手机验证码登录</strong>
                <small>由酷狗 API 发送</small>
              </div>
              <input data-role="country" type="hidden" value={kugou.country} />
              <div className="settings-phone-row kugou-phone-row">
                <label>
                  手机号
                  <input data-role="phone" className="light-input" inputMode="tel" autoComplete="tel" required value={kugou.phone} onChange={(event) => setKugou((prev) => ({ ...prev, phone: event.target.value }))} />
                </label>
                <button data-role="send" className="secondary-button" type="button" disabled={kugou.sendDisabled} onClick={() => void doSendCaptcha('kugou')}>
                  {kugou.sendLabel}
                </button>
              </div>
              <div className="settings-code-row">
                <label>
                  验证码
                  <input data-role="code" className="light-input" inputMode="numeric" autoComplete="one-time-code" required value={kugou.code} onChange={(event) => setKugou((prev) => ({ ...prev, code: event.target.value }))} />
                </label>
                <button className="primary-button" type="submit" disabled={kugou.loginBusy}>
                  {kugou.loginBusy ? '正在登录' : '登录并保存'}
                </button>
              </div>
            </form>
            <button className="forget-button" data-role="clear" type="button" onClick={() => void clearCredential('kugou')}>
              清除酷狗凭据
            </button>
          </section>
        </div>
        {Toast}
      </main>
    </div>
  )
}