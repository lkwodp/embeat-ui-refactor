import type {
  ArtistRecommendResponse,
  HealthResponse,
  RecommendMultiRequest,
  RecommendResponse,
  SearchResponse,
} from '../types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    credentials: 'same-origin',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error((data as { error?: string }).error || `请求失败 (${response.status})`)
  }
  return data as T
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
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