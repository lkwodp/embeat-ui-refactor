import { useCallback, useEffect, useRef, useState } from 'react'
import type { Track } from '../types'
import {
  exportStatus,
  fetchPlatformPlaylists,
  fetchPlatformStatus,
  savePlatformConfig,
  startExport,
} from '../api/client'
import type { PlatformStatus } from '../types'

export interface ExportModalHook {
  visible: boolean
  tracks: Track[]
  open: (items: Track[]) => void
  close: () => void
}

export function useExportModal(): ExportModalHook {
  const [visible, setVisible] = useState(false)
  const [tracks, setTracks] = useState<Track[]>([])
  const open = useCallback((items: Track[]) => {
    setTracks(items)
    setVisible(true)
  }, [])
  const close = useCallback(() => setVisible(false), [])
  return { visible, tracks, open, close }
}

interface PlatformProgressState {
  status: string
  phase: string
  current: string
  processed: number
  total: number
  percent: number
}

const initialProgress: PlatformProgressState = {
  status: 'queued',
  phase: '等待开始',
  current: '正在创建任务',
  processed: 0,
  total: 0,
  percent: 0,
}

export function ExportModal({ hook, onToast }: { hook: ExportModalHook; onToast: (message: string) => void }) {
  const [target, setTarget] = useState<'netease' | 'kugou' | 'both'>('netease')
  const [platformReady, setPlatformReady] = useState<{ netease: boolean; kugou: boolean }>({ netease: false, kugou: false })
  const [neteaseStatus, setNeteaseStatus] = useState<PlatformStatus | null>(null)
  const [kugouStatus, setKugouStatus] = useState<PlatformStatus | null>(null)
  const [neteasePlaylists, setNeteasePlaylists] = useState<{ id: string; name: string; trackCount: number }[]>([])
  const [kugouPlaylists, setKugouPlaylists] = useState<{ id: string; name: string; trackCount: number }[]>([])
  const [neteasePlaylist, setNeteasePlaylist] = useState('NEW')
  const [kugouPlaylist, setKugouPlaylist] = useState('NEW')
  const [neteaseNewName, setNeteaseNewName] = useState('')
  const [kugouNewName, setKugouNewName] = useState('')
  const [neteaseApi, setNeteaseApi] = useState('')
  const [neteaseProxy, setNeteaseProxy] = useState('')
  const [neteaseCookie, setNeteaseCookie] = useState('')
  const [kugouApi, setKugouApi] = useState('')
  const [kugouProxy, setKugouProxy] = useState('')
  const [kugouCookie, setKugouCookie] = useState('')
  const [progressMode, setProgressMode] = useState(false)
  const [resultMode, setResultMode] = useState(false)
  const [resultHtml, setResultHtml] = useState('')
  const [progress, setProgress] = useState<{ netease: PlatformProgressState; kugou: PlatformProgressState }>({ netease: { ...initialProgress }, kugou: { ...initialProgress } })
  const [connectBusy, setConnectBusy] = useState<{ netease: boolean; kugou: boolean }>({ netease: false, kugou: false })
  const [refreshBusy, setRefreshBusy] = useState<{ netease: boolean; kugou: boolean }>({ netease: false, kugou: false })
  const [selectedCount, setSelectedCount] = useState(0)
  const jobIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (hook.visible) {
      setSelectedCount(hook.tracks.length)
      setProgressMode(false)
      setResultMode(false)
      setResultHtml('')
      setProgress({ netease: { ...initialProgress }, kugou: { ...initialProgress } })
      void preparePlatforms()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hook.visible])

  useEffect(() => {
    if (hook.visible) void preparePlatforms()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, hook.visible])

  const requestedPlatforms = useCallback((): ('netease' | 'kugou')[] => {
    if (target === 'both') return ['netease', 'kugou']
    return [target]
  }, [target])

  async function preparePlatforms() {
    for (const platform of requestedPlatforms()) {
      try {
        const status = await fetchPlatformStatus(platform)
        if (platform === 'netease') {
          setNeteaseStatus(status)
          if (status.configured) {
            setPlatformReady((prev) => ({ ...prev, netease: true }))
            await loadPlaylists('netease')
          }
        } else {
          setKugouStatus(status)
          if (status.configured) {
            setPlatformReady((prev) => ({ ...prev, kugou: true }))
            if (status.api_url) setKugouApi(status.api_url)
            if (status.proxy_url) setKugouProxy(status.proxy_url)
            await loadPlaylists('kugou')
          }
        }
      } catch (error) {
        onToast((error as Error).message)
      }
    }
  }

  async function loadPlaylists(platform: 'netease' | 'kugou') {
    setRefreshBusy((prev) => ({ ...prev, [platform]: true }))
    try {
      const result = await fetchPlatformPlaylists(platform)
      if (platform === 'netease') setNeteasePlaylists(result.playlists)
      else setKugouPlaylists(result.playlists)
    } catch (error) {
      onToast((error as Error).message)
    } finally {
      setRefreshBusy((prev) => ({ ...prev, [platform]: false }))
    }
  }

  async function connectPlatform(platform: 'netease' | 'kugou') {
    const apiUrl = platform === 'netease' ? neteaseApi : kugouApi
    const cookie = platform === 'netease' ? neteaseCookie : kugouCookie
    const proxyUrl = platform === 'netease' ? neteaseProxy : kugouProxy
    if (!apiUrl || !cookie) return onToast('请填写 API 地址和 Cookie')
    setConnectBusy((prev) => ({ ...prev, [platform]: true }))
    try {
      const result = await savePlatformConfig(platform, { api_url: apiUrl, proxy_url: proxyUrl, cookie })
      if (platform === 'netease') {
        setNeteaseCookie('')
        setNeteaseStatus(result)
        setPlatformReady((prev) => ({ ...prev, netease: true }))
        await loadPlaylists('netease')
      } else {
        setKugouCookie('')
        setKugouStatus(result)
        setPlatformReady((prev) => ({ ...prev, kugou: true }))
        await loadPlaylists('kugou')
      }
    } catch (error) {
      onToast((error as Error).message)
    } finally {
      setConnectBusy((prev) => ({ ...prev, [platform]: false }))
    }
  }

  async function forgetPlatform(platform: 'netease' | 'kugou') {
    try {
      await savePlatformConfig(platform, { clear: true })
      if (platform === 'netease') {
        setPlatformReady((prev) => ({ ...prev, netease: false }))
        setNeteaseCookie('')
      } else {
        setPlatformReady((prev) => ({ ...prev, kugou: false }))
        setKugouCookie('')
      }
      onToast('已清除当前用户的网易云凭据')
    } catch (error) {
      onToast((error as Error).message)
    }
  }

  function resetProgress() {
    const platforms = requestedPlatforms()
    setProgress({
      netease: platforms.includes('netease') ? { ...initialProgress, total: hook.tracks.length } : { ...initialProgress },
      kugou: platforms.includes('kugou') ? { ...initialProgress, total: hook.tracks.length } : { ...initialProgress },
    })
  }

  function updatePlatformProgress(platform: 'netease' | 'kugou', item: PlatformProgressState) {
    setProgress((prev) => ({ ...prev, [platform]: item }))
  }

  function delay(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  async function waitForExport(jobId: string) {
    while (true) {
      await delay(500)
      const job = await exportStatus(jobId)
      Object.entries(job.platforms || {}).forEach(([platform, item]) => {
        const p = platform as 'netease' | 'kugou'
        updatePlatformProgress(p, {
          status: item.status,
          phase: item.phase || '处理中',
          current: item.current || (item.status === 'queued' ? '等待前一个平台完成' : '请稍候'),
          processed: item.processed || 0,
          total: item.total || 0,
          percent: Number(item.percent) || 0,
        })
      })
      if (job.status === 'completed') return job.result
      if (job.status === 'failed') throw new Error(job.error || '导入任务失败')
    }
  }

  function renderPlatformExportResult(platform: string, result: any): string {
    const platformName = platform === 'netease' ? '网易云音乐' : '酷狗音乐'
    if (!result.ok) {
      return `<div class="result-failure"><h3>${platformName}保存失败</h3><p>${escapeHtml(result.error || '未知错误')}</p></div>`
    }
    const failures = result.failed || []
    const matched = result.matched || []
    const skippedExisting = result.skipped_existing || []
    const nameKey = platform === 'netease' ? 'netease_name' : 'kugou_name'
    const artistKey = platform === 'netease' ? 'netease_artist' : 'kugou_artist'
    return `
      <div class="platform-result">
        <div class="result-success"><h3>${platformName}保存完成</h3><p>新增 ${result.added} 首，目标歌单原有重复 ${result.skipped} 首，匹配失败 ${failures.length} 首。</p><p>目标歌单 ID：${escapeHtml(result.playlist_id)}</p></div>
        ${matched.length ? `<details class="mapping-details" open><summary>新增匹配明细（${matched.length}）</summary><div class="mapping-list">${matched.map((item: any) => `${escapeHtml(item.track_name)} - ${escapeHtml(item.artist_name)} → <strong>${escapeHtml(item[nameKey])}</strong> - ${escapeHtml(item[artistKey])} <em>${Math.round(Number(item.match_score || 0) * 100)}%</em>`).join('<br>')}</div></details>` : ''}
        ${skippedExisting.length ? `<details class="mapping-details"><summary>歌单已有歌曲（${skippedExisting.length}）</summary><div class="mapping-list">${skippedExisting.map((item: any) => `${escapeHtml(item.track_name)} - ${escapeHtml(item.artist_name)} → ${escapeHtml(item[nameKey])} - ${escapeHtml(item[artistKey])}`).join('<br>')}</div></details>` : ''}
        ${failures.length ? `<div class="failed-list">${failures.map((item: any) => `${escapeHtml(item.track_name)} - ${escapeHtml(item.artist_name)}：${escapeHtml(item.reason)}`).join('<br>')}</div>` : ''}
      </div>`
  }

  async function doExport() {
    if (!hook.tracks.length) return onToast('请至少选择一首歌曲')
    const missing = requestedPlatforms().filter((platform) => !platformReady[platform])
    if (missing.length) return onToast(`请先连接${missing.map((platform) => (platform === 'netease' ? '网易云' : '酷狗')).join('和')}`)
    if (requestedPlatforms().includes('netease') && neteasePlaylist === 'NEW' && !neteaseNewName.trim()) return onToast('请填写网易云新歌单名称')
    if (requestedPlatforms().includes('kugou') && kugouPlaylist === 'NEW' && !kugouNewName.trim()) return onToast('请填写酷狗新歌单名称')
    setProgressMode(true)
    setResultMode(false)
    resetProgress()
    try {
      const started = await startExport({
        target,
        netease: { playlist_id: neteasePlaylist, playlist_name: neteaseNewName.trim() },
        kugou: { playlist_id: kugouPlaylist, playlist_name: kugouNewName.trim() },
        tracks: hook.tracks.map(({ track_name, artist_name, track_name_zh, artist_name_zh }) => ({ track_name, artist_name, track_name_zh, artist_name_zh })),
      })
      jobIdRef.current = started.job_id
      const result = await waitForExport(started.job_id)
      setProgressMode(false)
      setResultMode(true)
      setResultHtml(
        `${Object.entries(result?.targets || {}).map(([platform, platformResult]) => renderPlatformExportResult(platform, platformResult)).join('')}`,
      )
    } catch (error) {
      setProgressMode(false)
      onToast((error as Error).message)
    }
  }

  if (!hook.visible) return null

  const neteasePanel = platformReady.netease ? 'netease-export' : 'netease-auth'
  const kugouPanel = platformReady.kugou ? 'kugou-export' : 'kugou-auth'
  const showNetease = requestedPlatforms().includes('netease')
  const showKugou = requestedPlatforms().includes('kugou')

  return (
    <div id="netease-modal" className="modal" role="dialog" aria-modal="true" aria-labelledby="netease-title">
      <div className="modal-backdrop" onClick={hook.close}></div>
      <div className="modal-card">
        <div className="modal-header">
          <div>
            <p className="eyebrow">Playlist Export</p>
            <h2 id="netease-title">保存到歌单</h2>
          </div>
          <button className="modal-close" type="button" aria-label="关闭" onClick={hook.close}>
            ×
          </button>
        </div>

        {!progressMode && !resultMode ? (
          <>
            <div className="modal-section export-target-section">
              <strong>保存目标</strong>
              <div id="export-target" className="segmented-control" role="radiogroup" aria-label="保存目标">
                <label>
                  <input type="radio" name="export-target" value="netease" checked={target === 'netease'} onChange={() => setTarget('netease')} />
                  <span>网易云</span>
                </label>
                <label>
                  <input type="radio" name="export-target" value="kugou" checked={target === 'kugou'} onChange={() => setTarget('kugou')} />
                  <span>酷狗</span>
                </label>
                <label>
                  <input type="radio" name="export-target" value="both" checked={target === 'both'} onChange={() => setTarget('both')} />
                  <span>两个都保存</span>
                </label>
              </div>
            </div>

            <div id="netease-auth" className={`modal-section platform-panel ${showNetease && neteasePanel === 'netease-auth' ? '' : 'hidden'}`} data-export-platform="netease">
              <div className="platform-heading">
                <strong>网易云音乐</strong>
                <small>需要连接兼容 API</small>
              </div>
              <label htmlFor="netease-api">兼容 API 地址</label>
              <input id="netease-api" className="light-input" placeholder="https://your-netease-api.example.com" autoComplete="off" value={neteaseApi} onChange={(event) => setNeteaseApi(event.target.value)} />
              <label htmlFor="netease-proxy">
                本机 HTTP 代理 <small>直连被拦截时使用</small>
              </label>
              <input id="netease-proxy" className="light-input" placeholder="http://127.0.0.1:8080 可留空" autoComplete="off" value={neteaseProxy} onChange={(event) => setNeteaseProxy(event.target.value)} />
              <label htmlFor="netease-cookie">网易云 Cookie</label>
              <textarea id="netease-cookie" className="light-input cookie-input" placeholder="MUSIC_U=...; __csrf=..." autoComplete="off" value={neteaseCookie} onChange={(event) => setNeteaseCookie(event.target.value)} />
              <p className="security-note">Cookie 保存在当前浏览器中，用于 UI 服务重启后自动恢复登录。</p>
              <button id="netease-connect" className="primary-button modal-primary" type="button" disabled={connectBusy.netease} onClick={() => void connectPlatform('netease')}>
                {connectBusy.netease ? '正在校验…' : '校验并连接'}
              </button>
            </div>

            <div id="netease-export" className={`modal-section platform-panel ${showNetease && neteasePanel === 'netease-export' ? '' : 'hidden'}`} data-export-platform="netease">
              <div className="platform-heading">
                <strong>网易云音乐</strong>
                <small>目标歌单</small>
              </div>
              <div className="account-strip">
                <span className="status-dot"></span>
                <strong>已连接</strong>
                <small>
                  UID <span id="netease-uid">{neteaseStatus?.uid}</span>
                </small>
              </div>
              <button id="netease-forget" className="forget-button" type="button" onClick={() => void forgetPlatform('netease')}>
                清除浏览器保存的网易云凭据
              </button>
              <label htmlFor="netease-playlist">目标歌单</label>
              <div className="playlist-row">
                <select id="netease-playlist" className="light-input" value={neteasePlaylist} onChange={(event) => setNeteasePlaylist(event.target.value)}>
                  <option value="NEW">＋ 新建歌单</option>
                  {neteasePlaylists.map((playlist) => (
                    <option key={playlist.id} value={playlist.id}>
                      {playlist.name} ({playlist.trackCount} 首)
                    </option>
                  ))}
                </select>
                <button id="netease-refresh" className="icon-button" type="button" title="刷新歌单" disabled={refreshBusy.netease} onClick={() => void loadPlaylists('netease')}>
                  ↻
                </button>
              </div>
              <input id="netease-new-name" className={`light-input ${neteasePlaylist === 'NEW' ? '' : 'hidden'}`} placeholder="Embeat 推荐收藏" value={neteaseNewName} onChange={(event) => setNeteaseNewName(event.target.value)} />
            </div>

            <div id="kugou-auth" className={`modal-section platform-panel ${showKugou && kugouPanel === 'kugou-auth' ? '' : 'hidden'}`} data-export-platform="kugou">
              <div className="platform-heading">
                <strong>酷狗音乐</strong>
                <small>未检测到有效磁盘凭据</small>
              </div>
              <label htmlFor="kugou-api">酷狗兼容 API 地址</label>
              <input id="kugou-api" className="light-input" placeholder="https://your-kugou-api.example.com" autoComplete="off" value={kugouApi} onChange={(event) => setKugouApi(event.target.value)} />
              <label htmlFor="kugou-proxy">
                本机 HTTP 代理 <small>直连被拦截时使用</small>
              </label>
              <input id="kugou-proxy" className="light-input" placeholder="http://127.0.0.1:8080 可留空" autoComplete="off" value={kugouProxy} onChange={(event) => setKugouProxy(event.target.value)} />
              <label htmlFor="kugou-cookie">酷狗 Cookie</label>
              <textarea id="kugou-cookie" className="light-input cookie-input" placeholder="token=...; userid=...; dfid=..." autoComplete="off" value={kugouCookie} onChange={(event) => setKugouCookie(event.target.value)} />
              <p className="security-note">校验成功后写入本机凭据文件，后续重启无需再次输入。</p>
              <button id="kugou-connect" className="primary-button modal-primary" type="button" disabled={connectBusy.kugou} onClick={() => void connectPlatform('kugou')}>
                {connectBusy.kugou ? '正在校验…' : '校验并保存'}
              </button>
            </div>

            <div id="kugou-export" className={`modal-section platform-panel ${showKugou && kugouPanel === 'kugou-export' ? '' : 'hidden'}`} data-export-platform="kugou">
              <div className="platform-heading">
                <strong>酷狗音乐</strong>
                <small>目标歌单</small>
              </div>
              <div className="account-strip">
                <span className="status-dot"></span>
                <strong>已连接</strong>
                <small>
                  UID <span id="kugou-uid">{kugouStatus?.userid || kugouStatus?.uid}</span>
                </small>
              </div>
              <label htmlFor="kugou-playlist">目标歌单</label>
              <div className="playlist-row">
                <select id="kugou-playlist" className="light-input" value={kugouPlaylist} onChange={(event) => setKugouPlaylist(event.target.value)}>
                  <option value="NEW">＋ 新建歌单</option>
                  {kugouPlaylists.map((playlist) => (
                    <option key={playlist.id} value={playlist.id}>
                      {playlist.name} ({playlist.trackCount} 首)
                    </option>
                  ))}
                </select>
                <button id="kugou-refresh" className="icon-button" type="button" title="刷新歌单" disabled={refreshBusy.kugou} onClick={() => void loadPlaylists('kugou')}>
                  ↻
                </button>
              </div>
              <input id="kugou-new-name" className={`light-input ${kugouPlaylist === 'NEW' ? '' : 'hidden'}`} placeholder="Embeat 推荐收藏" value={kugouNewName} onChange={(event) => setKugouNewName(event.target.value)} />
            </div>

            <div id="export-controls" className="modal-section export-controls">
              <div className="export-summary">
                <strong id="selected-count">{selectedCount}</strong>
                <span>首推荐歌曲待匹配</span>
              </div>
              <button id="netease-submit" className="primary-button modal-primary" type="button" onClick={() => void doExport()}>
                开始匹配并保存
              </button>
            </div>
          </>
        ) : null}

        {progressMode ? (
          <div id="netease-progress" className="modal-section">
            <strong className="progress-heading">保存进度</strong>
            <div id="netease-platform-progress" className="platform-progress" data-status={progress.netease.status}>
              <div className="platform-progress-title">
                <strong>网易云音乐</strong>
                <span id="netease-progress-phase">{progress.netease.phase}</span>
              </div>
              <div className="progress-track">
                <div id="netease-progress-bar" className="progress-bar" style={{ width: `${progress.netease.percent}%` }}></div>
              </div>
              <div className="progress-meta">
                <span id="netease-progress-count">
                  {progress.netease.processed} / {progress.netease.total}
                </span>
                <strong id="netease-progress-percent">{progress.netease.percent}%</strong>
              </div>
              <p id="netease-progress-current">{progress.netease.current}</p>
            </div>
            <div id="kugou-platform-progress" className={`platform-progress ${requestedPlatforms().includes('kugou') ? '' : 'hidden'}`} data-status={progress.kugou.status}>
              <div className="platform-progress-title">
                <strong>酷狗音乐</strong>
                <span id="kugou-progress-phase">{progress.kugou.phase}</span>
              </div>
              <div className="progress-track">
                <div id="kugou-progress-bar" className="progress-bar kugou-progress-bar" style={{ width: `${progress.kugou.percent}%` }}></div>
              </div>
              <div className="progress-meta">
                <span id="kugou-progress-count">
                  {progress.kugou.processed} / {progress.kugou.total}
                </span>
                <strong id="kugou-progress-percent">{progress.kugou.percent}%</strong>
              </div>
              <p id="kugou-progress-current">{progress.kugou.current}</p>
            </div>
          </div>
        ) : null}

        {resultMode ? (
          <div className="modal-section">
            <div id="netease-result" dangerouslySetInnerHTML={{ __html: resultHtml }} />
            <button className="secondary-button" type="button" onClick={hook.close}>
              关闭
            </button>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function escapeHtml(value: string | null | undefined): string {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' } as Record<string, string>)[char])
}