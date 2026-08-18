import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  discoverGenre,
  discoverGenres,
  discoverWeekly,
  fetchHistory,
  recommendArtist,
  recommendMulti,
  recommendTrack,
  searchTracks,
} from '../api/client'
import type { HistoryItem, Track } from '../types'
import { AccountBadge, BackButton, BrandRow, ServiceStatus, useToast } from '../components/common'
import { ExportModal, useExportModal } from '../components/ExportModal'

const sourceNames: Record<string, string> = {
  similar: '声学相似',
  popular: '流派热门',
  same_artist: '同艺人',
  related_artist: '相似艺人',
  related_track: '歌单关联',
}

const RADIO_HANDOFF_KEY = 'embeat_ui_radio_handoff_v1'

function initial(value: string | null | undefined): string {
  return Array.from(value || '?')[0]?.toUpperCase() ?? '?'
}

function splitGenres(value: string): string[] {
  return String(value || '').split(',').map((item) => item.trim()).filter(Boolean)
}

function genreLabel(genre: string, genreZh: Record<string, string>): string {
  const zh = genreZh[genre]
  return zh ? `${zh} · ${genre}` : genre
}

interface Discovery {
  type: 'weekly' | 'genre'
  genre?: string
}

type ViewName = 'empty' | 'candidates' | 'recommendations' | 'loading' | 'history'

export function Home() {
  const { showToast, Toast } = useToast()
  const [queryMode, setQueryModeState] = useState<'song' | 'artist' | 'track_artist'>('song')
  const [trackName, setTrackName] = useState('')
  const [artistName, setArtistName] = useState('')
  const [trackId, setTrackId] = useState('')
  const [view, setView] = useState<ViewName>('empty')
  const [loadingTitle, setLoadingTitle] = useState('正在查询')
  const [loadingDetail, setLoadingDetail] = useState('连接 4500 万首歌曲')
  const [eyebrow, setEyebrow] = useState('歌曲搜索')
  const [title, setTitle] = useState('选择一首歌')
  const [meta, setMeta] = useState('')

  const [candidates, setCandidates] = useState<Track[]>([])
  const [candidatePage, setCandidatePage] = useState(1)
  const [candidatePageSize, setCandidatePageSize] = useState(10)
  const [candidateSummary, setCandidateSummary] = useState('')
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<Set<string>>(new Set())

  const [currentTracks, setCurrentTracks] = useState<Track[]>([])
  const [seeds, setSeeds] = useState<Track[]>([])
  const [currentArtist, setCurrentArtist] = useState<{ input_name: string; artist_name: string; artist_name_zh: string } | null>(null)
  const [discovery, setDiscovery] = useState<Discovery | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [resultLimit, setResultLimit] = useState(20)
  const [resultPageSize, setResultPageSize] = useState(10)
  const [resultSort, setResultSort] = useState<'score' | 'popularity' | 'seed_hits'>('score')
  const [popularityMin, setPopularityMin] = useState(0)
  const [activeSources, setActiveSources] = useState<Set<string>>(new Set())
  const [activeGenres, setActiveGenres] = useState<Set<string>>(new Set())
  const [selectedTrackIds, setSelectedTrackIds] = useState<Set<string>>(new Set())

  const [genreOptions, setGenreOptions] = useState<string[]>([])
  const [genreSelect, setGenreSelect] = useState('')
  const [genreZh, setGenreZh] = useState<Record<string, string>>({})
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([])

  const exportModal = useExportModal()
  const seedPanelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    void fetch(`${import.meta.env.BASE_URL}genres-zh.json`, { credentials: 'same-origin' })
      .then((response) => (response.ok ? response.json() : {}))
      .then((data) => setGenreZh(data && typeof data === 'object' ? (data as Record<string, string>) : {}))
      .catch(() => setGenreZh({}))
  }, [])

  const loadGenreOptions = useCallback(async () => {
    if (genreOptions.length) return
    try {
      const data = await discoverGenres(300)
      setGenreOptions(data.genres)
    } catch {
      /* health polling will surface database errors */
    }
  }, [genreOptions.length])

  useEffect(() => {
    void loadGenreOptions()
  }, [loadGenreOptions])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const fromRadio = params.get('from') === 'playlist-radio'
    if (fromRadio) {
      try {
        const payload = JSON.parse(sessionStorage.getItem(RADIO_HANDOFF_KEY) || 'null')
        sessionStorage.removeItem(RADIO_HANDOFF_KEY)
        if (payload?.data?.tracks?.length) {
          renderRecommendations(payload.data)
          const context = payload.context || {}
          const platformName = context.platform_name || (context.platform === 'kugou' ? '酷狗音乐' : '网易云音乐')
          const playlistName = context.playlist_name || '歌单'
          setTitle(`${playlistName} · 电台`)
          setRecommendationSummary(`${platformName}《${playlistName}》共 ${context.playlist_total || 0} 首，抽取 ${context.sampled || 0} 首并成功映射 ${context.matched || payload.data.seeds?.length || 0} 首种子。`)
          const unmatched = Array.isArray(context.unmatched) ? context.unmatched.length : 0
          showToast(`已载入歌单电台：${payload.data.tracks.length} 首推荐${unmatched ? `，${unmatched} 首抽样歌曲未映射` : ''}`)
        }
      } catch {
        /* ignore malformed handoff */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setRecommendationSummary = useCallback((text: string) => {
    setRecommendationSummaryText(text)
  }, [])
  const [recommendationSummaryText, setRecommendationSummaryText] = useState('')
  const [seedPanelHtml, setSeedPanelHtml] = useState('')

  function setQueryMode(mode: 'song' | 'artist' | 'track_artist') {
    setQueryModeState(mode)
  }

  function showView(name: ViewName) {
    setView(name)
  }

  function setLoading(text: string, detail: string) {
    showView('loading')
    setLoadingTitle(text)
    setLoadingDetail(detail)
    setEyebrow('Embeat')
    setTitle(text)
    setMeta('')
  }

  function showEmpty() {
    showView('empty')
    setEyebrow(queryMode === 'artist' ? '歌手推荐' : '歌曲搜索')
    setTitle(queryMode === 'artist' ? '选择一个歌手' : '选择一首歌')
    setMeta('')
  }

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault()
    const name = trackName.trim()
    const artist = artistName.trim()
    if (queryMode === 'artist') {
      if (!artist) return showToast('请输入歌手名')
      return void loadArtistRecommendations(artist)
    }
    if (!name) return showToast('请输入歌曲名')
    if (queryMode === 'track_artist' && !artist) {
      return showToast('请同时输入歌手名')
    }
    const combined = queryMode === 'track_artist'
    setLoading(combined ? '正在匹配歌曲与歌手' : '正在搜索歌曲', combined ? '确认数据库中的准确版本' : '匹配数据库中的曲名与版本')
    try {
      const data = await searchTracks(name, combined ? artist : '', 50)
      if (combined && data.tracks.length === 1) {
        showToast('已找到唯一匹配版本，正在生成推荐')
        return void loadRecommendations(data.tracks[0].track_id)
      }
      if (combined && data.tracks.length === 0) {
        showToast(`数据库中没有“${name}”这首歌，已回退到 ${artist} 的歌手推荐`)
        return void loadArtistRecommendations(artist)
      }
      renderCandidates(data.tracks, name, combined ? artist : '')
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  function handleIdSubmit(event: React.FormEvent) {
    event.preventDefault()
    const id = trackId.trim()
    if (id) void loadRecommendations(id)
  }

  async function loadRecommendations(trackId: string, limit = resultLimit || 20) {
    if (!trackId) return
    setLoading('正在生成推荐', '执行多路召回与融合排序')
    try {
      const data = await recommendTrack(trackId, limit)
      renderRecommendations(data)
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  async function loadArtistRecommendations(artistNameValue: string, limit = resultLimit || 20) {
    const name = String(artistNameValue || '').trim()
    if (!name) return showToast('请输入歌手名')
    setLoading('正在生成歌手电台', `提取 ${name} 的整体声学特征`)
    try {
      const data = await recommendArtist(name, limit)
      renderRecommendations(data)
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  async function loadRecommendationsForSeeds(trackIds: string[], title = '', limit = resultLimit || 50) {
    const ids = Array.from(new Set(trackIds.filter(Boolean)))
    if (!ids.length) return showToast('请至少选择一首种子歌曲')
    if (ids.length === 1) return void loadRecommendations(ids[0], limit)
    setLoading('正在生成多曲电台', `融合 ${ids.length} 首种子的推荐结果`)
    try {
      const data = await recommendMulti({ track_ids: ids, limit, history_title: title || `${ids.length} 首种子电台` })
      renderRecommendations(data)
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  function loadMultiSeedRecommendations() {
    void loadRecommendationsForSeeds(Array.from(selectedCandidateIds))
  }

  function renderCandidates(tracks: Track[], name: string, artist: string) {
    setCurrentArtist(null)
    setDiscovery(null)
    showView('candidates')
    setEyebrow('歌曲搜索')
    setTitle(artist ? `${name} · ${artist}` : name)
    setMeta(`<strong>${tracks.length}</strong> 个候选版本`)
    setCandidateSummary(tracks.length ? (artist ? '已按歌手缩小范围，请确认录音室、Live 或翻唱版本' : '选择准确的歌曲版本') : '没有找到匹配歌曲，可尝试繁体曲名、英文艺人名或 Spotify ID')
    setCandidates(tracks)
    setCandidatePage(1)
    setSelectedCandidateIds(new Set())
  }

  const candidatePages = useMemo(() => Math.max(1, Math.ceil(candidates.length / candidatePageSize)), [candidates, candidatePageSize])
  const candidatePageTracks = useMemo(
    () => candidates.slice((candidatePage - 1) * candidatePageSize, candidatePage * candidatePageSize),
    [candidates, candidatePage, candidatePageSize],
  )

  function renderRecommendations(data: any) {
    const artistMode = data?.mode === 'artist' && data?.artist
    const seedList: Track[] = Array.isArray(data?.seeds) ? data.seeds : data?.seed ? [data.seed] : []
    if (!Array.isArray(data?.tracks) || (!artistMode && !seedList.length)) {
      showToast('该历史记录缺少完整推荐结果，无法恢复')
      return false
    }
    const tracks = data.tracks
    const elapsed = Number(data.elapsed_ms || 0)
    const seed = seedList[0] || data.representative_track || {}
    setSeeds(artistMode ? [] : seedList)
    setCurrentArtist(artistMode ? data.artist : null)
    setDiscovery(null)
    setCurrentTracks(tracks)
    setSelectedTrackIds(new Set(tracks.map((track: Track) => track.track_id)))
    setCurrentPage(1)
    setActiveSources(new Set())
    setActiveGenres(new Set())
    showView('recommendations')
    setEyebrow(artistMode ? '歌手推荐' : '推荐结果')
    setTitle(artistMode ? data.artist.artist_name_zh || data.artist.artist_name || data.artist.input_name : seedList.length > 1 ? `${seedList.length} 首种子电台` : seed.track_name)
    setMeta(`<strong>${tracks.length}</strong> 首 · ${elapsed} ms`)
    if (artistMode) {
      const representative = data.representative_track || {}
      setRecommendationSummary(`基于 ${data.artist.artist_name_zh || data.artist.artist_name} 的整体声学特征。代表曲目：${representative.track_name_zh || representative.track_name || '未知'}`)
      setSeedPanelHtml(
        `<div class="track-art"><span>♫</span></div><div><h2>${escapeHtml(data.artist.artist_name_zh || data.artist.artist_name || data.artist.input_name)}</h2><p>${escapeHtml(data.artist.artist_name)} · 歌手整体风格推荐</p><small>代表曲目：${escapeHtml(representative.track_name_zh || representative.track_name || '未知歌曲')}</small></div>`,
      )
    } else {
      setRecommendationSummary(seedList.length > 1 ? `融合 ${seedList.map((item) => item.track_name_zh).slice(0, 4).join('、')}${seedList.length > 4 ? '…' : ''}` : `基于 ${seed.artist_name} · ${seed.album_name}`)
      setSeedPanelHtml(
        seedList.length > 1
          ? `<div class="track-art"><span>${escapeHtml(initial(seed.track_name))}</span></div><div><h2>${escapeHtml(`${seedList.length} 首歌曲共同作为种子`)}</h2><p>${escapeHtml(seedList.map((item) => `${item.track_name_zh} - ${item.artist_name_zh}`).slice(0, 5).join(' · '))}</p><small>Multi-seed radio</small></div>`
          : `<div class="track-art"><span>${escapeHtml(initial(seed.track_name))}</span></div><div><h2>${escapeHtml(seed.track_name)}</h2><p>${escapeHtml(seed.artist_name)} · ${escapeHtml(seed.album_name)}</p><small>${escapeHtml(seed.track_id)}</small></div>`,
      )
    }
    setSelectAllRef(true)
    renderResultRows()
    return true
  }

  const [selectAllRef, setSelectAllRef] = useState(true)
  const [selectAllIndeterminate, setSelectAllIndeterminate] = useState(false)

  const filteredTracks = useMemo(() => {
    const minimumPopularity = popularityMin / 100
    let tracks = currentTracks.filter((track) => {
      const sourceOk = !activeSources.size || track.sources.some((source) => activeSources.has(source))
      const genres = splitGenres(track.artist_genres)
      const genreOk = !activeGenres.size || genres.some((genre) => activeGenres.has(genre))
      return sourceOk && genreOk && track.popularity >= minimumPopularity
    })
    tracks = [...tracks].sort((a, b) => {
      if (resultSort === 'popularity') return b.popularity - a.popularity || b.score - a.score
      if (resultSort === 'seed_hits') return (b.seed_hits || 1) - (a.seed_hits || 1) || b.score - a.score
      return b.score - a.score || b.popularity - a.popularity
    })
    return tracks
  }, [currentTracks, activeSources, activeGenres, popularityMin, resultSort])

  const resultPages = useMemo(() => Math.max(1, Math.ceil(filteredTracks.length / resultPageSize)), [filteredTracks, resultPageSize])
  const pageTracks = useMemo(
    () => filteredTracks.slice((currentPage - 1) * resultPageSize, currentPage * resultPageSize),
    [filteredTracks, currentPage, resultPageSize],
  )

  const sourceFilters = useMemo(() => Array.from(new Set(currentTracks.flatMap((track) => track.sources))).sort(), [currentTracks])
  const genreFilters = useMemo(() => {
    const counts = new Map<string, number>()
    currentTracks.flatMap((track) => splitGenres(track.artist_genres)).forEach((genre) => counts.set(genre, (counts.get(genre) || 0) + 1))
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([genre]) => genre)
  }, [currentTracks])

  function renderResultRows() {
    const pages = resultPages
    setCurrentPage((page) => Math.min(page, pages))
  }

  useEffect(() => {
    renderResultRows()
  }, [filteredTracks, resultPageSize]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleResultPageChange(page: number) {
    setCurrentPage(page)
  }

  function toggleTrackSelection(trackId: string) {
    setSelectedTrackIds((prev) => {
      const next = new Set(prev)
      if (next.has(trackId)) next.delete(trackId)
      else next.add(trackId)
      return next
    })
  }

  function handleSelectAllChange(checked: boolean) {
    setSelectedTrackIds((prev) => {
      const next = new Set(prev)
      filteredTracks.forEach((track) => (checked ? next.add(track.track_id) : next.delete(track.track_id)))
      return next
    })
    setSelectAllRef(checked)
  }

  useEffect(() => {
    const filteredSelected = filteredTracks.filter((track) => selectedTrackIds.has(track.track_id)).length
    setSelectAllRef(filteredTracks.length > 0 && filteredSelected === filteredTracks.length)
    setSelectAllIndeterminate(filteredSelected > 0 && filteredSelected < filteredTracks.length)
  }, [filteredTracks, selectedTrackIds])

  function handleFilterClick(filter: 'source' | 'genre', value: string) {
    if (filter === 'source') {
      setActiveSources((prev) => {
        const next = new Set(prev)
        if (next.has(value)) next.delete(value)
        else next.add(value)
        return next
      })
    } else {
      setActiveGenres((prev) => {
        const next = new Set(prev)
        if (next.has(value)) next.delete(value)
        else next.add(value)
        return next
      })
    }
    setCurrentPage(1)
  }

  async function loadWeeklyDiscovery(limit = resultLimit || 50) {
    setLoading('每周新发现', '生成本周轮换发现榜')
    try {
      const data = await discoverWeekly(limit)
      renderDiscovery(data.tracks, `每周新发现 · ${data.week}`, data.note, { type: 'weekly' })
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  async function loadGenreDiscovery(requestedGenre = '', limit = resultLimit || 50) {
    const genre = requestedGenre || genreSelect
    if (!genre) return showToast('请选择流派')
    setGenreSelect(genre)
    setLoading('按流派找歌', `正在读取 ${genre}`)
    try {
      const data = await discoverGenre(genre, limit)
      renderDiscovery(data.tracks, data.genre, '按热度浏览该流派', { type: 'genre', genre: data.genre })
    } catch (error) {
      showEmpty()
      showToast((error as Error).message)
    }
  }

  function renderDiscovery(tracks: Track[], title: string, note: string, discoveryContext: Discovery | null) {
    setSeeds([])
    setCurrentArtist(null)
    setDiscovery(discoveryContext)
    setCurrentTracks(tracks)
    setSelectedTrackIds(new Set(tracks.map((track) => track.track_id)))
    setCurrentPage(1)
    setActiveSources(new Set())
    setActiveGenres(new Set())
    showView('recommendations')
    setEyebrow('Discover')
    setTitle(title)
    setRecommendationSummary(note || '')
    setSeedPanelHtml(`<div class="track-art"><span>✦</span></div><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(note || '')}</p><small>Discovery collection</small></div>`)
    renderResultRows()
  }

  async function renderHistory() {
    showView('history')
    setEyebrow('Account History')
    setTitle('最近搜索与推荐')
    try {
      const result = await fetchHistory('', 1, 100)
      const items = result.items.map((item) => {
        const summary = (item.summary || {}) as Record<string, unknown>
        return { ...item, type: item.kind, data: { ...summary, tracks: Array.isArray(item.tracks) ? item.tracks : summary.tracks } } as HistoryItem & { type: string; data: any }
      })
      setHistoryItems(items)
      setMeta(`<strong>${items.length}</strong> 条记录`)
    } catch (error) {
      showToast((error as Error).message)
    }
  }

  function restoreHistoryItem(item: HistoryItem & { type: string; data: any }) {
    if (!Array.isArray(item.data?.tracks)) return showToast('该旧历史记录没有保存完整结果，无法恢复')
    if (item.type === 'search') return renderCandidates(item.data.tracks, item.data.name || item.title, item.data.artist || '')
    if (item.type === 'genre' || item.type === 'weekly' || item.type === 'discover') {
      return renderDiscovery(item.data.tracks, item.data.discoveryTitle || item.title, item.data.note || '', null)
    }
    if (item.type === 'artist_recommend') {
      if (!item.data?.artist) return showToast('该歌手电台历史记录缺少歌手信息，无法恢复')
      return renderRecommendations(item.data)
    }
    if (item.type === 'recommend' || item.type === 'radio') return renderRecommendations(item.data)
    showToast('该类型的历史记录暂不支持恢复')
  }

  async function exportHistory() {
    try {
      const result = await fetchHistory('', 1, 100)
      const items = result.items.map((item) => {
        const summary = (item.summary || {}) as Record<string, unknown>
        return { ...item, type: item.kind, data: { ...summary, tracks: Array.isArray(item.tracks) ? item.tracks : summary.tracks } } as HistoryItem & { type: string; data: any }
      })
      setHistoryItems(items)
      const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json;charset=utf-8' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `embeat-history-${new Date().toISOString().slice(0, 10)}.json`
      link.click()
      setTimeout(() => URL.revokeObjectURL(link.href), 1000)
    } catch (error) {
      showToast((error as Error).message)
    }
  }

  function historyKindLabel(kind: string) {
    return ({ search: '搜索', recommend: '单曲推荐', radio: '多曲电台', artist_recommend: '歌手电台', genre: '流派浏览', weekly: '每周发现', discover: '发现' } as Record<string, string>)[kind] || '记录'
  }

  function paginationButtons(current: number, pages: number) {
    return Array.from({ length: pages }, (_, index) => (
      <button key={index} type="button" data-page={index + 1} className={index + 1 === current ? 'active' : ''} onClick={() => handleResultPageChange(index + 1)}>
        {index + 1}
      </button>
    ))
  }

  const selectedTracks = useMemo(() => currentTracks.filter((track) => selectedTrackIds.has(track.track_id)), [currentTracks, selectedTrackIds])

  function openExportModal() {
    if (!selectedTracks.length) return showToast('请先选择至少一首推荐歌曲')
    exportModal.open(selectedTracks)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <BrandRow />
        <form id="search-form" className={`search-form`} data-mode={queryMode} onSubmit={handleSearch}>
          <div className="query-mode" role="radiogroup" aria-label="推荐查询方式">
            <label>
              <input type="radio" name="query-mode" value="song" checked={queryMode === 'song'} onChange={() => setQueryMode('song')} />
              <span>歌曲</span>
            </label>
            <label>
              <input type="radio" name="query-mode" value="artist" checked={queryMode === 'artist'} onChange={() => setQueryMode('artist')} />
              <span>歌手</span>
            </label>
            <label>
              <input type="radio" name="query-mode" value="track_artist" checked={queryMode === 'track_artist'} onChange={() => setQueryMode('track_artist')} />
              <span>歌曲+歌手</span>
            </label>
          </div>
          <div id="track-field" className={`query-field ${queryMode === 'artist' ? 'hidden' : ''}`}>
            <label htmlFor="track-name">歌曲</label>
            <div className="input-wrap">
              <span aria-hidden="true">⌕</span>
              <input id="track-name" name="track-name" placeholder="旅行的意义" autoComplete="off" required={queryMode !== 'artist'} value={trackName} onChange={(event) => setTrackName(event.target.value)} />
            </div>
          </div>
          <div id="artist-field" className={`query-field ${queryMode === 'song' ? 'hidden' : ''}`}>
            <label htmlFor="artist-name">
              艺人 <small id="artist-hint">{queryMode === 'artist' ? '支持中英文与别名' : '可选，可缩小范围'}</small>
            </label>
            <div className="input-wrap">
              <span aria-hidden="true">♪</span>
              <input id="artist-name" name="artist-name" placeholder={queryMode === 'song' ? '田馥甄' : '陈绮贞 / Cheer Chen'} autoComplete="off" required={queryMode === 'artist'} value={artistName} onChange={(event) => setArtistName(event.target.value)} />
            </div>
          </div>
          <button id="search-button" className="primary-button" type="submit">
            {queryMode === 'artist' ? '搜索歌手' : '搜索歌曲'}
          </button>
        </form>

        <div className="divider">
          <span>或</span>
        </div>

        <form id="id-form" className="id-form" onSubmit={handleIdSubmit}>
          <label htmlFor="track-id">Spotify Track ID</label>
          <div className="input-wrap mono-input">
            <span aria-hidden="true">#</span>
            <input id="track-id" name="track-id" placeholder="1ZeVIrCWzEmsJexkrgvjFv" autoComplete="off" value={trackId} onChange={(event) => setTrackId(event.target.value)} />
          </div>
          <button className="secondary-button" type="submit">
            直接推荐
          </button>
        </form>

        <ServiceStatus />
        <div className="sidebar-tools">
          <button id="history-open" className="sidebar-tool" type="button" onClick={() => void renderHistory()}>
            最近记录
          </button>
          <button id="history-export" className="sidebar-tool" type="button" onClick={exportHistory}>
            导出历史 JSON
          </button>
          <a className="sidebar-tool" href="/settings">
            平台账号配置
          </a>
        </div>
        <div className="discover-tools">
          <a className="discover-button discover-link" href="/radio">
            歌单电台
          </a>
          <button id="weekly-discover" className="discover-button" type="button" onClick={() => void loadWeeklyDiscovery()}>
            每周新发现
          </button>
          <div className="genre-browser">
            <select id="genre-select" value={genreSelect} onChange={(event) => setGenreSelect(event.target.value)}>
              <option value="">按流派找歌</option>
              {genreOptions.map((genre) => (
                <option key={genre} value={genre}>
                  {genreLabel(genre, genreZh)}
                </option>
              ))}
            </select>
            <button id="genre-browse" type="button" onClick={() => void loadGenreDiscovery()}>
              浏览
            </button>
          </div>
        </div>
        <AccountBadge />
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div className="topbar-heading">
            {view !== 'empty' && <BackButton onClick={showEmpty} />}
            <div>
              <p className="eyebrow" id="view-eyebrow">
                {eyebrow}
              </p>
              <h1 id="view-title">{title}</h1>
            </div>
          </div>
          <div className="topbar-meta" id="topbar-meta" dangerouslySetInnerHTML={{ __html: meta }} />
        </header>

        <section id="empty-state" className={`empty-state ${view === 'empty' ? '' : 'hidden'}`}>
          <div className="record-visual" aria-hidden="true">
            <div className="record">
              <div className="record-label">
                <span></span>
              </div>
            </div>
            <div className="sound-bars">
              <i></i>
              <i></i>
              <i></i>
              <i></i>
              <i></i>
              <i></i>
              <i></i>
            </div>
          </div>
          <h2 id="empty-title">从一首熟悉的歌开始</h2>
          <p id="empty-copy">输入曲名，选择数据库中的准确版本。</p>
        </section>

        <section id="candidate-view" className={`content-view ${view === 'candidates' ? '' : 'hidden'}`} aria-live="polite">
          <div className="section-heading">
            <div>
              <h2>搜索结果</h2>
              <p id="candidate-summary">{candidateSummary}</p>
            </div>
            <div className="recommend-actions">
              <select
                id="candidate-page-size"
                className="compact-select"
                aria-label="搜索结果每页数量"
                value={candidatePageSize}
                onChange={(event) => {
                  setCandidatePageSize(Number(event.target.value))
                  setCandidatePage(1)
                }}
              >
                <option value="5">每页 5 条</option>
                <option value="10">每页 10 条</option>
                <option value="20">每页 20 条</option>
              </select>
              <button id="multi-seed-button" className="netease-button" type="button" onClick={loadMultiSeedRecommendations}>
                用选中歌曲生成电台
              </button>
            </div>
          </div>
          <div id="candidate-list" className="candidate-list">
            {candidatePageTracks.map((track) => (
              <button
                key={track.track_id}
                className="candidate"
                type="button"
                data-track-id={track.track_id}
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest('.candidate-check')) return
                  void loadRecommendations(track.track_id)
                }}
              >
                <input
                  className="candidate-check"
                  type="checkbox"
                  value={track.track_id}
                  checked={selectedCandidateIds.has(track.track_id)}
                  onChange={(event) => {
                    setSelectedCandidateIds((prev) => {
                      const next = new Set(prev)
                      if (event.target.checked) next.add(track.track_id)
                      else next.delete(track.track_id)
                      return next
                    })
                  }}
                  aria-label="选择为电台种子"
                />
                <span className="track-art">
                  <span>{initial(track.track_name)}</span>
                </span>
                <span className="track-copy">
                  <strong>{track.track_name}</strong>
                  <span>
                    {track.artist_name} · {track.album_name}
                  </span>
                  <small>{track.track_id}</small>
                </span>
                <span className="arrow" aria-hidden="true">
                  ›
                </span>
              </button>
            ))}
          </div>
          <div id="candidate-pagination" className="pagination">
            {candidatePages > 1 ? paginationButtons(candidatePage, candidatePages) : null}
          </div>
        </section>

        <section id="recommend-view" className={`content-view ${view === 'recommendations' ? '' : 'hidden'}`} aria-live="polite">
          <div id="seed-panel" className="seed-panel" ref={seedPanelRef} dangerouslySetInnerHTML={{ __html: seedPanelHtml }} />
          <div className="section-heading recommendations-heading">
            <div>
              <h2>推荐歌曲</h2>
              <p id="recommend-summary">{recommendationSummaryText}</p>
            </div>
            <div className="recommend-actions">
              <label className="select-all">
                <input
                  id="select-all"
                  type="checkbox"
                  checked={selectAllRef}
                  onChange={(event) => handleSelectAllChange(event.target.checked)}
                  ref={(node) => {
                    if (node) node.indeterminate = selectAllIndeterminate
                  }}
                />{' '}
                全选
              </label>
              <select
                id="result-limit"
                className="compact-select"
                aria-label="推荐总数"
                value={resultLimit}
                onChange={(event) => {
                  const value = Number(event.target.value)
                  setResultLimit(value)
                  if (discovery?.type === 'weekly') return void loadWeeklyDiscovery(value)
                  if (discovery?.type === 'genre' && discovery.genre) return void loadGenreDiscovery(discovery.genre, value)
                  if (currentArtist) return void loadArtistRecommendations(currentArtist.input_name || currentArtist.artist_name, value)
                  if (seeds.length > 1) return void loadRecommendationsForSeeds(seeds.map((seed) => seed.track_id), '', value)
                  return void loadRecommendations(seeds[0]?.track_id, value)
                }}
              >
                <option value="10">获取 10 首</option>
                <option value="20">获取 20 首</option>
                <option value="30">获取 30 首</option>
                <option value="50">获取 50 首</option>
                <option value="100">获取 100 首</option>
              </select>
              <select id="result-page-size" className="compact-select" aria-label="推荐结果每页数量" value={resultPageSize} onChange={(event) => { setResultPageSize(Number(event.target.value)); setCurrentPage(1) }}>
                <option value="5">每页 5 条</option>
                <option value="10">每页 10 条</option>
                <option value="20">每页 20 条</option>
              </select>
              <select id="result-sort" className="compact-select" value={resultSort} onChange={(event) => { setResultSort(event.target.value as 'score' | 'popularity' | 'seed_hits'); setCurrentPage(1) }}>
                <option value="score">按匹配度</option>
                <option value="popularity">按热度</option>
                <option value="seed_hits">按种子覆盖</option>
              </select>
              <button id="netease-open" className="netease-button" type="button" onClick={openExportModal}>
                保存到歌单
              </button>
            </div>
          </div>
          <div id="result-filters" className="result-filters">
            <span>来源</span>
            <div id="source-filters" className="filter-chips">
              {sourceFilters.map((source) => (
                <button key={source} className={`filter-chip ${activeSources.has(source) ? 'active' : ''}`} type="button" data-filter="source" data-value={source} onClick={() => handleFilterClick('source', source)}>
                  {sourceNames[source] || source}
                </button>
              ))}
            </div>
            <span>流派</span>
            <div id="genre-filters" className="filter-chips">
              {genreFilters.length ? genreFilters.map((genre) => (
                <button key={genre} className={`filter-chip ${activeGenres.has(genre) ? 'active' : ''}`} type="button" data-filter="genre" data-value={genre} onClick={() => handleFilterClick('genre', genre)}>
                  {genre}
                </button>
              )) : <small>无流派数据</small>}
            </div>
            <label className="popularity-filter">
              最低热度 <input id="popularity-min" type="range" min="0" max="100" value={popularityMin} onChange={(event) => { setPopularityMin(Number(event.target.value)); setCurrentPage(1) }} />
              <b id="popularity-value">{popularityMin}</b>
            </label>
          </div>
          <div className="result-table-wrap">
            <table className="result-table">
              <thead>
                <tr>
                  <th>选择</th>
                  <th>数据库名称</th>
                  <th>简体中文显示</th>
                  <th>专辑</th>
                  <th>召回来源</th>
                  <th>匹配度</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="result-list">
                {pageTracks.map((track) => (
                  <tr key={track.track_id}>
                    <td>
                      <input className="track-check" type="checkbox" value={track.track_id} checked={selectedTrackIds.has(track.track_id)} onChange={() => toggleTrackSelection(track.track_id)} aria-label={`选择 ${track.track_name}`} />
                    </td>
                    <td className="song-cell">
                      <strong>{track.track_name}</strong>
                      <span>{track.artist_name}</span>
                    </td>
                    <td className="song-cell">
                      <strong>{track.track_name_zh}</strong>
                      <span>{track.artist_name_zh}</span>
                    </td>
                    <td className="album-cell" title={track.album_name}>
                      {track.album_name}
                    </td>
                    <td>
                      <div className="source-list">
                        {track.sources.map((source) => (
                          <span key={source} className="source">
                            {sourceNames[source] || source}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="score">{Math.round(track.score * 100)}%</td>
                    <td>
                      <button className="recommend-again" type="button" data-track-id={track.track_id} title="以此歌曲继续推荐" onClick={() => void loadRecommendations(track.track_id)}>
                        ›
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div id="result-cards" className="result-cards">
            {pageTracks.map((track) => (
              <article key={track.track_id} className="result-card">
                <div className="result-card-head">
                  <input className="track-check" type="checkbox" value={track.track_id} checked={selectedTrackIds.has(track.track_id)} onChange={() => toggleTrackSelection(track.track_id)} aria-label={`选择 ${track.track_name}`} />
                  <div className="result-card-title">
                    <strong>{track.track_name}</strong>
                    <span>{track.artist_name}</span>
                  </div>
                  <span className="result-card-score">{Math.round(track.score * 100)}%</span>
                </div>
                <div className="result-card-zh">
                  <strong>{track.track_name_zh}</strong> · {track.artist_name_zh}
                </div>
                <div className="result-card-meta">
                  <span>热度 {Math.round(track.popularity * 100)}</span>
                  <span>{track.album_name}</span>
                  {splitGenres(track.artist_genres).slice(0, 2).map((genre) => (
                    <span key={genre}>{genre}</span>
                  ))}
                </div>
                <div className="result-card-actions">
                  <div className="source-list">
                    {track.sources.map((source) => (
                      <span key={source} className="source">
                        {sourceNames[source] || source}
                      </span>
                    ))}
                  </div>
                  <button className="recommend-again" type="button" data-track-id={track.track_id} onClick={() => void loadRecommendations(track.track_id)}>
                    ›
                  </button>
                </div>
              </article>
            ))}
          </div>
          <div id="pagination" className="pagination">
            {paginationButtons(currentPage, resultPages)}
          </div>
        </section>

        <section id="history-view" className={`content-view ${view === 'history' ? '' : 'hidden'}`} aria-live="polite">
          <div className="section-heading">
            <div>
              <h2>最近记录</h2>
              <p>保存在当前浏览器中</p>
            </div>
          </div>
          <div id="history-list" className="history-list">
            {historyItems.length ? (
              historyItems.map((item) => (
                <article key={item.id} className="history-item">
                  <div>
                    <strong>{item.title}</strong>
                    <span>
                      {historyKindLabel(item.kind)} · {new Date(item.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <button type="button" data-history-id={item.id} onClick={() => restoreHistoryItem(item as HistoryItem & { type: string; data: any })}>
                    恢复
                  </button>
                </article>
              ))
            ) : (
              <p>暂无历史记录。</p>
            )}
          </div>
        </section>

        <section id="loading-state" className={`loading-state ${view === 'loading' ? '' : 'hidden'}`} aria-live="polite">
          <div className="loader"></div>
          <strong id="loading-title">{loadingTitle}</strong>
          <span id="loading-detail">{loadingDetail}</span>
        </section>

        {Toast}
      </main>

      <ExportModal hook={exportModal} onToast={showToast} />
    </div>
  )
}

function escapeHtml(value: string | null | undefined): string {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' } as Record<string, string>)[char])
}
