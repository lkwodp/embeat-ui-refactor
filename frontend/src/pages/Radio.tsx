import { useEffect, useRef, useState } from 'react'
import {
  fetchConfig,
  fetchPlatformPlaylists,
  fetchPlatformStatus,
  playlistSeeds,
  recommendMulti,
  savePlatformConfig,
} from '../api/client'
import type { PlatformStatus, Track } from '../types'
import { AccountBadge, BackButton, BrandRow, useToast } from '../components/common'

const sourceNames: Record<string, string> = {
  similar: '声学相似',
  popular: '流派热门',
  same_artist: '同艺人',
  related_artist: '相似艺人',
  related_track: '歌单关联',
}

const platformNames: Record<string, string> = { netease: '网易云音乐', kugou: '酷狗音乐' }
const RADIO_HANDOFF_KEY = 'embeat_ui_radio_handoff_v1'

interface RadioStatus {
  status: 'loading' | 'online' | 'offline'
  title: string
  detail: string
}

interface Playlist {
  id: string
  name: string
  trackCount: number
}

export function Radio() {
  const { showToast, Toast } = useToast()
  const [platform, setPlatform] = useState<'netease' | 'kugou'>('netease')
  const [accountStatus, setAccountStatus] = useState<RadioStatus>({ status: 'loading', title: '正在检查登录状态', detail: '请稍候' })
  const [authOpen, setAuthOpen] = useState(false)
  const [api, setApi] = useState('')
  const [proxy, setProxy] = useState('')
  const [cookie, setCookie] = useState('')
  const [authNote, setAuthNote] = useState('')
  const [cookiePlaceholder, setCookiePlaceholder] = useState('')
  const [cookieLabel, setCookieLabel] = useState('')
  const [connectLabel, setConnectLabel] = useState('校验并连接')
  const [connectBusy, setConnectBusy] = useState(false)
  const [playlists, setPlaylists] = useState<Playlist[]>([])
  const [playlist, setPlaylist] = useState('')
  const [playlistDisabled, setPlaylistDisabled] = useState(true)
  const [playlistRefreshDisabled, setPlaylistRefreshDisabled] = useState(true)
  const [seedLimit, setSeedLimit] = useState('30')
  const [resultLimit, setResultLimit] = useState('50')
  const [generateDisabled, setGenerateDisabled] = useState(true)
  const [generateBusy, setGenerateBusy] = useState(false)
  const [progressVisible, setProgressVisible] = useState(false)
  const [progressPercent, setProgressPercent] = useState(0)
  const [progressPhase, setProgressPhase] = useState('准备读取歌单')
  const [progressDetail, setProgressDetail] = useState('正在准备')
  const [progressFailed, setProgressFailed] = useState(false)
  const [resultVisible, setResultVisible] = useState(false)
  const [resultSummary, setResultSummary] = useState('')
  const [seedChips, setSeedChips] = useState('')
  const [unmatched, setUnmatched] = useState<{ name: string; artist: string }[]>([])
  const [resultItems, setResultItems] = useState('')
  const [overviewTitle, setOverviewTitle] = useState('等待选择歌单')
  const [overviewPlaylist, setOverviewPlaylist] = useState('未选择')
  const [serviceTitle, setServiceTitle] = useState('正在连接')
  const [serviceDetail, setServiceDetail] = useState('Qdrant')
  const [serviceState, setServiceState] = useState<'connecting' | 'online' | 'offline'>('connecting')
  const [platformReady, setPlatformReady] = useState<{ netease: boolean; kugou: boolean }>({ netease: false, kugou: false })
  const platformStatusRef = useRef<Record<string, PlatformStatus>>({})

  const defaultsRef = { netease: { api: '', proxy: '' }, kugou: { api: '', proxy: '' } }

  useEffect(() => {
    let cancelled = false
    void prefillDefaults()
    async function init() {
      try {
        await prefillDefaults()
        if (cancelled) return
        renderAuthFields()
        updateOverview()
        await refreshPlatformStatus(true)
      } catch {
        /* ignore */
      }
    }
    void init()
    return () => {
      cancelled = true
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    renderAuthFields()
    updateOverview()
    void refreshPlatformStatus(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform])

  useEffect(() => {
    let cancelled = false
    async function checkHealth() {
      try {
        const response = await fetch('/api/health', { credentials: 'same-origin' })
        const health = await response.json().catch(() => ({}))
        if (cancelled) return
        if (!health.ready) {
          setServiceState('connecting')
          setServiceTitle('数据库初始化中')
          setServiceDetail('请稍候')
        } else {
          setServiceState('online')
          setServiceTitle('数据库在线')
          setServiceDetail(`${formatNumber(health.points)} 首歌曲`)
        }
      } catch {
        if (cancelled) return
        setServiceState('offline')
        setServiceTitle('数据库离线')
        setServiceDetail('检查 Qdrant')
      }
    }
    void checkHealth()
    const timer = window.setInterval(() => void checkHealth(), 5000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  function formatNumber(value: number | string): string {
    return new Intl.NumberFormat('zh-CN').format(Number(value))
  }

  async function prefillDefaults() {
    try {
      const defaults = await fetchConfig()
      defaultsRef.netease.api = defaults.netease_api_url || ''
      defaultsRef.kugou.api = defaults.kugou_api_url || ''
      defaultsRef.netease.proxy = defaults.proxy_url || ''
      defaultsRef.kugou.proxy = defaults.proxy_url || ''
    } catch {
      /* 默认值不可用时不提示 */
    }
  }

  function renderAuthFields() {
    const platformDefaults = platform === 'netease'
      ? { api: '', proxy: '', placeholder: 'MUSIC_U=...; __csrf=...', note: '网易云 Cookie 会保存在当前浏览器中，UI 服务重启后本页会自动恢复登录。' }
      : { api: '', proxy: '', placeholder: 'token=...; userid=...; dfid=...', note: '酷狗凭据校验成功后写入本机凭据文件，浏览器不会额外保存 Cookie。' }
    const currentStatus = platformStatusRef.current[platform] || {}
    setApi(String(currentStatus.api_url || platformDefaults.api || defaultsRef[platform].api || ''))
    setProxy(String(currentStatus.proxy_url ?? defaultsRef[platform].proxy ?? ''))
    setCookie('')
    setCookiePlaceholder(platformDefaults.placeholder)
    setCookieLabel(`${platformNames[platform]} Cookie`)
    setAuthNote(platformDefaults.note)
    setConnectLabel(platformReady[platform] ? '重新校验并连接' : '校验并连接')
    setAuthOpen(true)
  }

  function setAccountStatusUi(status: 'loading' | 'online' | 'offline', title: string, detail: string) {
    setAccountStatus({ status, title, detail })
  }

  async function refreshPlatformStatus(_tryRestore = false) {
    setAccountStatusUi('loading', `正在检查${platformNames[platform]}`, '读取登录状态与歌单权限')
    setPlaylistDisabled(true)
    try {
      const result = await fetchPlatformStatus(platform)
      platformStatusRef.current[platform] = result
      const ready = Boolean(result.configured)
      setPlatformReady((prev) => ({ ...prev, [platform]: ready }))
      renderAuthFields()
      if (!ready) {
        setAccountStatusUi('offline', `${platformNames[platform]}未连接`, '展开下方凭据区域完成连接')
        setAuthOpen(true)
        return
      }
      const accountId = result.uid || result.userid || ''
      setAccountStatusUi('online', `${platformNames[platform]}已连接`, accountId ? `UID ${accountId}` : '可以读取歌单')
      setAuthOpen(false)
      await loadPlaylists()
    } catch (error) {
      setPlatformReady((prev) => ({ ...prev, [platform]: false }))
      renderAuthFields()
      setAuthOpen(true)
      setAccountStatusUi('offline', `${platformNames[platform]}连接失败`, (error as Error).message)
    }
  }

  async function connectCurrentPlatform() {
    const apiUrl = api.trim()
    const proxyUrl = proxy.trim()
    const cookieValue = cookie.trim()
    if (!apiUrl || !cookieValue) return showToast('请填写 API 地址和 Cookie')
    setConnectBusy(true)
    setConnectLabel('正在校验…')
    try {
      const result = await savePlatformConfig(platform, { api_url: apiUrl, proxy_url: proxyUrl, cookie: cookieValue })
      setCookie('')
      platformStatusRef.current[platform] = { configured: true, api_url: apiUrl, proxy_url: proxyUrl, uid: result.uid, userid: result.userid }
      setPlatformReady((prev) => ({ ...prev, [platform]: true }))
      renderAuthFields()
      setAuthOpen(false)
      const accountId = result.uid || result.userid || ''
      setAccountStatusUi('online', `${platformNames[platform]}已连接`, accountId ? `UID ${accountId}` : '可以读取歌单')
      await loadPlaylists()
    } catch (error) {
      setPlatformReady((prev) => ({ ...prev, [platform]: false }))
      setAccountStatusUi('offline', `${platformNames[platform]}连接失败`, (error as Error).message)
      showToast((error as Error).message)
    } finally {
      setConnectBusy(false)
      setConnectLabel(platformReady[platform] ? '重新校验并连接' : '校验并连接')
    }
  }

  async function loadPlaylists() {
    if (!platformReady[platform]) return disablePlaylist()
    setPlaylistDisabled(true)
    setPlaylistRefreshDisabled(true)
    setPlaylists([])
    setPlaylist('')
    try {
      const result = await fetchPlatformPlaylists(platform)
      const items = (result.playlists || []).filter((item) => Number(item.trackCount) > 0)
      setPlaylists(items)
      setPlaylistDisabled(!items.length)
      setPlaylistRefreshDisabled(false)
    } catch (error) {
      setPlaylists([])
      setPlaylistDisabled(true)
      setPlaylistRefreshDisabled(false)
      showToast((error as Error).message)
    }
  }

  function disablePlaylist() {
    setPlaylists([])
    setPlaylist('')
    setPlaylistDisabled(true)
    setPlaylistRefreshDisabled(true)
  }

  function updateGenerateState() {
    setGenerateDisabled(!platformReady[platform] || !playlist)
  }

  function updateOverview() {
    const selected = playlists.find((item) => String(item.id) === playlist)
    setOverviewPlaylist(selected?.name || '未选择')
    setOverviewTitle(selected?.name || '等待选择歌单')
  }

  useEffect(() => {
    updateGenerateState()
  }, [platformReady, playlist]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    updateOverview()
  }, [playlist, playlists, seedLimit, resultLimit]) // eslint-disable-line react-hooks/exhaustive-deps

  async function generateRadio() {
    const playlistId = playlist
    const selected = playlists.find((item) => String(item.id) === playlistId)
    if (!playlistId || !selected) return showToast('请选择源歌单')
    setGenerateBusy(true)
    setResultVisible(false)
    setProgressVisible(true)
    setProgressPercent(12)
    setProgressPhase('读取源歌单')
    setProgressDetail(`正在从${platformNames[platform]}读取《${selected.name}》`)
    setProgressFailed(false)
    try {
      const seedData = await playlistSeeds(platform, playlistId, Number(seedLimit))
      if (!seedData.seeds?.length) throw new Error('抽取的歌曲均未能映射到 Embeat 数据库')
      setProgressPercent(62)
      setProgressPhase('融合多曲种子')
      setProgressDetail(`成功映射 ${seedData.seeds.length} 首，正在生成推荐`)
      const recommendation = await recommendMulti({
        track_ids: seedData.seeds.map((seed) => seed.track_id),
        limit: Number(resultLimit) || 50,
        history_title: `${platformNames[platform]}歌单电台 · ${selected.name}`,
      })
      setProgressPercent(100)
      setProgressPhase('电台生成完成')
      setProgressDetail(`已生成 ${recommendation.tracks.length} 首推荐歌曲`)
      const context = {
        platform,
        platform_name: platformNames[platform],
        playlist_id: playlistId,
        playlist_name: selected.name,
        playlist_total: seedData.playlist_total,
        sampled: seedData.sampled,
        matched: seedData.seeds.length,
        unmatched: seedData.unmatched || [],
      }
      const handoff = { data: recommendation, context }
      try {
        sessionStorage.setItem(RADIO_HANDOFF_KEY, JSON.stringify(handoff))
      } catch {
        /* optional handoff */
      }
      renderRadioResult(handoff)
    } catch (error) {
      setProgressPercent(0)
      setProgressPhase('生成失败')
      setProgressDetail((error as Error).message)
      setProgressFailed(true)
      showToast((error as Error).message)
    } finally {
      setGenerateBusy(false)
      updateGenerateState()
    }
  }

  function renderRadioResult(payload: { data: any; context: any }) {
    const { data, context } = payload
    setResultVisible(true)
    setResultSummary(`《${context.playlist_name}》共 ${context.playlist_total} 首，抽取 ${context.sampled} 首并成功映射 ${context.matched} 首；生成 ${data.tracks.length} 首推荐。`)
    setSeedChips(
      data.seeds
        .map(
          (seed: Track) =>
            `<span class="radio-seed-chip"><strong>${escapeHtml(seed.track_name_zh || seed.track_name)}</strong><small>${escapeHtml(seed.artist_name_zh || seed.artist_name)}</small></span>`,
        )
        .join(''),
    )
    const unmatchedItems = context.unmatched || []
    setUnmatched(unmatchedItems)
    setResultItems(
      data.tracks
        .map(
          (track: Track, index: number) =>
            `<article class="radio-result-item"><span class="radio-result-index">${index + 1}</span><div class="radio-result-copy"><strong>${escapeHtml(track.track_name_zh || track.track_name)}</strong><span>${escapeHtml(track.artist_name_zh || track.artist_name)}</span><small>${escapeHtml(track.track_name)} · ${escapeHtml(track.artist_name)}</small></div><div class="radio-result-meta"><strong>${Math.round(Number(track.score || 0) * 100)}%</strong><span>${(track.sources || []).map((source) => sourceNames[source] || source).join(' · ')}</span></div></article>`,
        )
        .join(''),
    )
    document.getElementById('radio-result')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function openInMainPage() {
    const handoffRaw = sessionStorage.getItem(RADIO_HANDOFF_KEY)
    if (!handoffRaw) return showToast('请先生成电台')
    window.location.href = '/?from=playlist-radio'
  }

  return (
    <div className="app-shell radio-page">
      <aside className="sidebar radio-sidebar">
        <BrandRow tagline="Playlist Radio" />
        <div className="radio-sidebar-copy">
          <p className="eyebrow">Radio Builder</p>
          <h2>歌单电台</h2>
          <p>网易云音乐 · 酷狗音乐</p>
        </div>
        <nav className="radio-nav" aria-label="页面导航">
          <a href="/">返回歌曲推荐</a>
          <a className="active" href="/radio" aria-current="page">
            歌单电台
          </a>
          <a href="/settings">平台账号配置</a>
        </nav>
        <div className={`service-status ${serviceState === 'online' ? 'online' : serviceState === 'offline' ? 'offline' : ''}`} id="radio-service-status">
          <span className="status-dot"></span>
          <div>
            <strong>{serviceTitle}</strong>
            <small>{serviceDetail}</small>
          </div>
        </div>
        <AccountBadge />
      </aside>

      <main className="workspace radio-workspace">
        <header className="topbar">
          <div className="topbar-heading">
            <BackButton />
            <div>
              <p className="eyebrow">Playlist Radio</p>
              <h1>用歌单生成电台</h1>
            </div>
          </div>
          <div className="topbar-meta">
            <strong>网易云 + 酷狗</strong>
            <br />
            均匀抽样 · 多曲融合
          </div>
        </header>

        <div className="radio-layout">
          <section className="radio-card radio-builder" aria-labelledby="radio-builder-title">
            <div className="section-heading">
              <div>
                <h2 id="radio-builder-title">选择歌单来源</h2>
                <p>只读取歌单，不会修改原歌单。</p>
              </div>
            </div>

            <div id="radio-platform" className="segmented-control radio-platform" role="radiogroup" aria-label="歌单平台">
              <label>
                <input type="radio" name="radio-platform" value="netease" checked={platform === 'netease'} onChange={() => setPlatform('netease')} />
                <span>网易云音乐</span>
              </label>
              <label>
                <input type="radio" name="radio-platform" value="kugou" checked={platform === 'kugou'} onChange={() => setPlatform('kugou')} />
                <span>酷狗音乐</span>
              </label>
            </div>

            <div id="radio-account-status" className="radio-account-status" data-status={accountStatus.status}>
              <span className="status-dot"></span>
              <div>
                <strong>{accountStatus.title}</strong>
                <small>{accountStatus.detail}</small>
              </div>
              <button id="radio-status-refresh" type="button" onClick={() => void refreshPlatformStatus(true)}>
                重新检查
              </button>
            </div>

            <details id="radio-auth" className={`radio-auth ${authOpen ? '' : 'hidden'}`}>
              <summary>连接或更新账号凭据</summary>
              <div className="radio-auth-fields">
                <label htmlFor="radio-api">兼容 API 地址</label>
                <input id="radio-api" className="light-input" autoComplete="off" value={api} onChange={(event) => setApi(event.target.value)} />
                <label htmlFor="radio-proxy">
                  本机 HTTP 代理 <small>可选</small>
                </label>
                <input id="radio-proxy" className="light-input" placeholder="http://127.0.0.1:8080 可留空" autoComplete="off" value={proxy} onChange={(event) => setProxy(event.target.value)} />
                <label htmlFor="radio-cookie">
                  <span id="radio-cookie-label">{cookieLabel}</span>
                </label>
                <textarea id="radio-cookie" className="light-input cookie-input" placeholder={cookiePlaceholder} autoComplete="off" value={cookie} onChange={(event) => setCookie(event.target.value)} />
                <p id="radio-auth-note" className="security-note">
                  {authNote}
                </p>
                <button id="radio-connect" className="primary-button" type="button" disabled={connectBusy} onClick={() => void connectCurrentPlatform()}>
                  {connectBusy ? '正在校验…' : connectLabel}
                </button>
              </div>
            </details>

            <div className="radio-field">
              <label htmlFor="radio-playlist">源歌单</label>
              <div className="playlist-row">
                <select id="radio-playlist" className="light-input" disabled={playlistDisabled} value={playlist} onChange={(event) => setPlaylist(event.target.value)}>
                  <option value="">{playlistDisabled ? '请先连接平台' : '选择一个源歌单'}</option>
                  {playlists.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({Number(item.trackCount) || 0} 首)
                    </option>
                  ))}
                </select>
                <button id="radio-playlist-refresh" className="icon-button" type="button" title="刷新歌单" disabled={playlistRefreshDisabled} onClick={() => void loadPlaylists()}>
                  ↻
                </button>
              </div>
            </div>

            <div className="radio-options">
              <label htmlFor="radio-seed-limit">
                最多抽取
                <select id="radio-seed-limit" className="light-input" value={seedLimit} onChange={(event) => setSeedLimit(event.target.value)}>
                  <option value="5">5 首种子</option>
                  <option value="10">10 首种子</option>
                  <option value="20">20 首种子</option>
                  <option value="30">30 首种子</option>
                </select>
              </label>
              <label htmlFor="radio-result-limit">
                推荐数量
                <select id="radio-result-limit" className="light-input" value={resultLimit} onChange={(event) => setResultLimit(event.target.value)}>
                  <option value="10">10 首推荐</option>
                  <option value="20">20 首推荐</option>
                  <option value="30">30 首推荐</option>
                  <option value="50">50 首推荐</option>
                  <option value="100">100 首推荐</option>
                </select>
              </label>
            </div>

            <button id="radio-generate" className="primary-button radio-generate" type="button" disabled={generateDisabled || generateBusy} onClick={() => void generateRadio()}>
              {generateBusy ? '生成中…' : '生成歌单电台'}
            </button>

            <div id="radio-progress" className={`radio-progress ${progressVisible ? '' : 'hidden'}`} aria-live="polite" data-status={progressFailed ? 'failed' : progressPercent >= 100 ? 'completed' : 'running'}>
              <div className="platform-progress-title">
                <strong id="radio-progress-phase">{progressPhase}</strong>
                <span id="radio-progress-percent">{progressPercent}%</span>
              </div>
              <div className="progress-track">
                <div id="radio-progress-bar" className="progress-bar" style={{ width: `${Math.max(0, Math.min(100, progressPercent))}%` }}></div>
              </div>
              <p id="radio-progress-detail">{progressDetail}</p>
            </div>
          </section>

          <aside className="radio-card radio-overview">
            <p className="eyebrow">Current Session</p>
            <h2 id="radio-overview-title">{overviewTitle}</h2>
            <dl>
              <div>
                <dt>平台</dt>
                <dd id="radio-overview-platform">{platformNames[platform]}</dd>
              </div>
              <div>
                <dt>源歌单</dt>
                <dd id="radio-overview-playlist">{overviewPlaylist}</dd>
              </div>
              <div>
                <dt>种子上限</dt>
                <dd id="radio-overview-seeds">{seedLimit} 首</dd>
              </div>
              <div>
                <dt>推荐数量</dt>
                <dd id="radio-overview-results">{resultLimit} 首</dd>
              </div>
            </dl>
            <div className="radio-privacy-note">
              <strong>源歌单只读</strong>
              <p>保存推荐歌曲仍由主页面单独确认。</p>
            </div>
          </aside>
        </div>

        <section id="radio-result" className={`content-view radio-result ${resultVisible ? '' : 'hidden'}`} aria-live="polite">
          <div className="section-heading recommendations-heading">
            <div>
              <h2>电台已生成</h2>
              <p id="radio-result-summary">{resultSummary}</p>
            </div>
            <button id="radio-open-main" className="netease-button" type="button" onClick={openInMainPage}>
              在主页面筛选与保存
            </button>
          </div>
          <div id="radio-seed-summary" className="radio-seed-summary" dangerouslySetInnerHTML={{ __html: seedChips }} />
          <details id="radio-unmatched-details" className={`mapping-details ${unmatched.length ? '' : 'hidden'}`}>
            <summary id="radio-unmatched-summary">未映射歌曲（{unmatched.length}）</summary>
            <div id="radio-unmatched-list" className="mapping-list">
              {unmatched.map((item, index) => (
                <span key={index}>
                  {escapeHtml(item.name)} - {escapeHtml(item.artist)}
                  <br />
                </span>
              ))}
            </div>
          </details>
          <div id="radio-result-list" className="radio-result-list" dangerouslySetInnerHTML={{ __html: resultItems }} />
        </section>

        {Toast}
      </main>
    </div>
  )
}

function escapeHtml(value: string | null | undefined): string {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' } as Record<string, string>)[char])
}