import type { Track } from '../types'

interface TrackListProps {
  tracks: Track[]
  title: string
  emptyCopy: string
  onSelect?: (track: Track) => void
}

export function TrackList({ tracks, title, emptyCopy, onSelect }: TrackListProps) {
  return (
    <section className="content-view">
      <div className="section-heading">
        <p className="eyebrow">{title}</p>
        <h2>{tracks.length ? `${tracks.length} 首` : ''}</h2>
      </div>
      {tracks.length === 0 ? (
        <p className="empty-copy">{emptyCopy}</p>
      ) : (
        <ul className="track-list">
          {tracks.map((track) => (
            <li key={track.track_id}>
              <button
                type="button"
                className="track-row"
                disabled={!onSelect}
                onClick={() => onSelect?.(track)}
              >
                <span className="track-art" aria-hidden="true">
                  {track.track_name.slice(0, 1)}
                </span>
                <span className="track-copy">
                  <strong>{track.track_name_zh || track.track_name}</strong>
                  <span>{track.artist_name_zh || track.artist_name} · {track.album_name}</span>
                  <small>{track.track_id}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}