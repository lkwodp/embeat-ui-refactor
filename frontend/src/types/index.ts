export interface Track {
  track_id: string
  track_name: string
  artist_name: string
  track_name_zh: string
  artist_name_zh: string
  album_name: string
  artist_genres: string
  popularity: number
  score: number
  match_score?: number | null
  seed_hits?: number
  sources: string[]
}

export interface SearchResponse {
  tracks: Track[]
}

export interface RecommendMultiRequest {
  track_ids: string[]
  limit?: number
  history_title?: string
}

export interface RecommendResponse {
  seed: Track | null
  seeds: Track[] | null
  tracks: Track[]
  elapsed_ms: number
}

export interface Artist {
  input_name: string
  artist_idx: number
  artist_name: string
  artist_name_zh: string
  artist_genres: string
}

export interface ArtistRecommendResponse {
  mode: string
  artist: Artist
  representative_track: Track
  tracks: Track[]
  elapsed_ms: number
}

export interface HealthResponse {
  ready: boolean
  points: number
  service: string
}

export interface AuthMeResponse {
  user: { id: number; username: string }
  auth_enabled: boolean
  open_access?: boolean
}

export interface ConfigDefaults {
  netease_api_url: string
  kugou_api_url: string
  proxy_url: string
}

export interface Preferences {
  theme: string | null
  accent_hue: number | null
}

export interface HistoryItem {
  id: number
  user_id: number
  kind: string
  title: string
  summary: Record<string, unknown> | null
  tracks: Track[] | null
  created_at: string
}

export interface HistoryResponse {
  items: HistoryItem[]
  page: number
  page_size: number
  total: number
}

export interface PlatformStatus {
  configured: boolean
  api_url?: string
  proxy_url?: string
  uid?: string
  userid?: string
  phone?: string
}

export interface PlatformPlaylistsResponse {
  playlists: { id: string; name: string; trackCount: number }[]
}

export interface PlaylistSeedsResponse {
  seeds?: Track[]
  playlist_total?: number
  sampled?: number
  unmatched?: { name: string; artist: string }[]
}

export interface ExportJob {
  job_id: string
}

export interface ExportProgress {
  status: string
  phase: string
  current: string
  processed: number
  total: number
  percent: number
}

export interface ExportStatus {
  status: string
  error?: string
  platforms: Record<string, ExportProgress>
  result?: Record<string, PlatformExportResult>
}

export interface PlatformExportResult {
  ok: boolean
  error?: string
  added: number
  skipped: number
  failed: { track_name: string; artist_name: string; reason?: string }[]
  matched: Record<string, string>[]
  skipped_existing: Record<string, string>[]
  playlist_id: string
}

export interface WeeklyDiscovery {
  tracks: Track[]
  week: string
  note: string
}

export interface GenreDiscovery {
  tracks: Track[]
  genre: string
}