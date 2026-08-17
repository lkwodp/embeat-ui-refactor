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
  sources: string[]
}

export interface SearchResponse {
  tracks: Track[]
}

export interface RecommendRequest {
  track_id: string
  limit?: number
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