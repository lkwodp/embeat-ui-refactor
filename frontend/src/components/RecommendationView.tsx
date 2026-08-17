import type {
  ArtistRecommendResponse,
  RecommendResponse,
  Track,
} from '../types'
import { TrackList } from './TrackList'

interface RecommendationViewProps {
  data: RecommendResponse | ArtistRecommendResponse
  onSelect: (track: Track) => void
}

export function RecommendationView({ data, onSelect }: RecommendationViewProps) {
  const isArtist = 'mode' in data && data.mode === 'artist'
  const recommendation = !isArtist ? (data as RecommendResponse) : null
  const seeds = recommendation?.seeds?.length
    ? recommendation.seeds
    : recommendation?.seed
      ? [recommendation.seed]
      : []
  const representative = isArtist ? (data as ArtistRecommendResponse).representative_track : null

  const title = isArtist
    ? (data as ArtistRecommendResponse).artist.artist_name_zh
      || (data as ArtistRecommendResponse).artist.artist_name
      || (data as ArtistRecommendResponse).artist.input_name
    : seeds.length > 1
      ? `${seeds.length} 首种子电台`
      : seeds[0]?.track_name || '推荐结果'

  const subtitle = isArtist
    ? `基于 ${(data as ArtistRecommendResponse).artist.artist_name} 的整体声学特征`
    : seeds.length > 1
      ? `融合 ${seeds.map((item) => item.track_name_zh || item.track_name).slice(0, 4).join('、')}`
      : seeds[0]
        ? `基于 ${seeds[0].artist_name} · ${seeds[0].album_name}`
        : ''

  return (
    <section className="content-view">
      <div className="section-heading">
        <p className="eyebrow">{isArtist ? '歌手推荐' : '推荐结果'}</p>
        <h2>{title}</h2>
        <p className="empty-copy">{subtitle}</p>
      </div>

      {representative && (
        <div className="representative">
          <strong>代表曲目</strong>
          <span>{representative.track_name_zh || representative.track_name}</span>
        </div>
      )}

      <TrackList
        tracks={data.tracks}
        title="推荐曲目"
        emptyCopy="暂无推荐结果"
        onSelect={onSelect}
      />
    </section>
  )
}