import { useState } from 'react'
import { recommendArtist, recommendTrack, searchTracks } from '../api/client'
import { RecommendationView } from '../components/RecommendationView'
import { SearchForm, type QueryMode } from '../components/SearchForm'
import { TrackList } from '../components/TrackList'
import type { ArtistRecommendResponse, RecommendResponse, Track } from '../types'

export function Home() {
  const [mode, setMode] = useState<QueryMode>('song')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [candidates, setCandidates] = useState<Track[] | null>(null)
  const [recommendations, setRecommendations] = useState<RecommendResponse | ArtistRecommendResponse | null>(null)

  const handleSubmit = async (name: string, artist: string) => {
    setError('')
    setLoading(true)
    setRecommendations(null)
    try {
      if (mode === 'artist') {
        const data = await recommendArtist(name)
        setCandidates(null)
        setRecommendations(data)
      } else {
        const data = await searchTracks(name, mode === 'track_artist' ? artist : '', 50)
        setCandidates(data.tracks)
        if (mode === 'track_artist' && data.tracks.length === 1) {
          const recommendation = await recommendTrack(data.tracks[0].track_id)
          setRecommendations(recommendation)
        }
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError))
    } finally {
      setLoading(false)
    }
  }

  const handleSelectTrack = async (track: Track) => {
    setError('')
    setLoading(true)
    try {
      const data = await recommendTrack(track.track_id)
      setRecommendations(data)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : String(requestError))
    } finally {
      setLoading(false)
    }
  }

  const handleReselect = (track: Track) => {
    void handleSelectTrack(track)
  }

  return (
    <main className="home">
      <SearchForm
        mode={mode}
        onModeChange={setMode}
        onSubmit={handleSubmit}
        disabled={loading}
      />

      {error && <p className="error-banner">{error}</p>}
      {loading && <p className="loading-copy">正在生成推荐…</p>}

      {candidates && !loading && (
        <TrackList
          tracks={candidates}
          title={mode === 'track_artist' ? '候选版本' : '搜索候选'}
          emptyCopy="没有找到匹配歌曲，可尝试繁体曲名、英文艺人名"
          onSelect={handleSelectTrack}
        />
      )}

      {recommendations && !loading && (
        <RecommendationView data={recommendations} onSelect={handleReselect} />
      )}
    </main>
  )
}