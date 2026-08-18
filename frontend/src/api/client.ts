import type {
  ArtistRecommendResponse,
  AuthMeResponse,
  ConfigDefaults,
  ExportJob,
  ExportStatus,
  GenreDiscovery,
  HealthResponse,
  HistoryResponse,
  PlatformPlaylistsResponse,
  PlatformStatus,
  PlaylistSeedsResponse,
  Preferences,
  RecommendMultiRequest,
  RecommendResponse,
  SearchResponse,
  WeeklyDiscovery,
} from '../types'

const BASE = '/api'

export class ApiError extends Error {}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    credentials: 'same-origin',
  })
  const data = await response.json().catch(() => ({}))
  if (response.status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('embeat-auth-required'))
  }
  if (!response.ok) {
    throw new ApiError((data as { error?: string }).error || `请求失败 (${response.status})`)
  }
  return data as T
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  return request<AuthMeResponse>('/auth/me')
}

export async function login(username: string, password: string): Promise<AuthMeResponse> {
  return request<AuthMeResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
}

export async function register(username: string, password: string, inviteCode = ''): Promise<AuthMeResponse> {
  return request<AuthMeResponse>('/auth/register', { method: 'POST', body: JSON.stringify({ username, password, invite_code: inviteCode }) })
}

export async function pairDevice(code: string): Promise<AuthMeResponse> {
  return request<AuthMeResponse>('/device/pair', { method: 'POST', body: JSON.stringify({ code }) })
}

export async function logout(): Promise<void> {
  await request<{ ok: boolean }>('/auth/logout', { method: 'POST', body: '{}' })
}

export async function fetchConfig(): Promise<ConfigDefaults> {
  return request<ConfigDefaults>('/config')
}

export async function fetchPreferences(): Promise<Preferences> {
  return request<Preferences>('/preferences')
}

export async function savePreferences(payload: Partial<Preferences>): Promise<Preferences> {
  return request<Preferences>('/preferences', { method: 'POST', body: JSON.stringify(payload) })
}

export async function searchTracks(name: string, artist = '', limit = 50): Promise<SearchResponse> {
  const params = new URLSearchParams({ name, artist, limit: String(limit) })
  return request<SearchResponse>(`/search?${params}`)
}

export async function recommendTrack(trackId: string, limit = 20): Promise<RecommendResponse> {
  return request<RecommendResponse>('/recommend', {
    method: 'POST',
    body: JSON.stringify({ track_id: trackId, limit }),
  })
}

export async function recommendMulti(requestBody: RecommendMultiRequest): Promise<RecommendResponse> {
  return request<RecommendResponse>('/recommend/multi', {
    method: 'POST',
    body: JSON.stringify(requestBody),
  })
}

export async function recommendArtist(name: string, limit = 20): Promise<ArtistRecommendResponse> {
  const params = new URLSearchParams({ name, limit: String(limit) })
  return request<ArtistRecommendResponse>(`/recommend/artist?${params}`)
}

export async function discoverWeekly(limit = 50): Promise<WeeklyDiscovery> {
  return request<WeeklyDiscovery>(`/discover/weekly?limit=${limit}`)
}

export async function discoverGenre(genre: string, limit = 50): Promise<GenreDiscovery> {
  return request<GenreDiscovery>(`/discover/genre?genre=${encodeURIComponent(genre)}&limit=${limit}`)
}

export async function discoverGenres(limit = 300): Promise<{ genres: string[] }> {
  return request<{ genres: string[] }>(`/discover/genres?limit=${limit}`)
}

export async function fetchPlatformStatus(platform: 'netease' | 'kugou'): Promise<PlatformStatus> {
  return request<PlatformStatus>(`/${platform}/status`)
}

export async function savePlatformConfig(
  platform: 'netease' | 'kugou',
  payload: Record<string, unknown>,
): Promise<PlatformStatus> {
  return request<PlatformStatus>(`/${platform}/config`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function fetchPlatformPlaylists(platform: 'netease' | 'kugou'): Promise<PlatformPlaylistsResponse> {
  return request<PlatformPlaylistsResponse>(`/${platform}/playlists`)
}

export async function sendCaptcha(
  platform: 'netease' | 'kugou',
  payload: { phone: string; api_url: string; proxy_url?: string; country_code?: string },
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/${platform}/captcha/send`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function loginCaptcha(
  platform: 'netease' | 'kugou',
  payload: { phone: string; code: string; api_url: string; proxy_url?: string; country_code?: string },
): Promise<PlatformStatus> {
  return request<PlatformStatus>(`/${platform}/captcha/login`, { method: 'POST', body: JSON.stringify(payload) })
}

export async function playlistSeeds(
  platform: 'netease' | 'kugou',
  playlistId: string,
  maxSeeds = 30,
): Promise<PlaylistSeedsResponse> {
  const params = new URLSearchParams({ platform, id: playlistId, max_seeds: String(maxSeeds) })
  return request<PlaylistSeedsResponse>(`/playlist/seeds?${params}`)
}

export async function startExport(payload: {
  target: 'netease' | 'kugou' | 'both'
  netease: { playlist_id: string; playlist_name: string }
  kugou: { playlist_id: string; playlist_name: string }
  tracks: { track_name: string; artist_name: string; track_name_zh?: string; artist_name_zh?: string }[]
}): Promise<ExportJob> {
  return request<ExportJob>('/export/start', { method: 'POST', body: JSON.stringify(payload) })
}

export async function exportStatus(jobId: string): Promise<ExportStatus> {
  return request<ExportStatus>(`/export/status?id=${encodeURIComponent(jobId)}`)
}

export async function fetchHistory(kind = '', page = 1, pageSize = 30): Promise<HistoryResponse> {
  const params = new URLSearchParams({ kind, page: String(page), page_size: String(pageSize) })
  return request<HistoryResponse>(`/history?${params}`)
}

export async function addHistory(payload: {
  kind?: string
  title: string
  summary?: unknown
  tracks?: unknown
}): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/history', { method: 'POST', body: JSON.stringify(payload) })
}