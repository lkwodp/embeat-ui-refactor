import { useState } from 'react'
import type { FormEvent } from 'react'

export type QueryMode = 'song' | 'artist' | 'track_artist'

interface SearchFormProps {
  mode: QueryMode
  onModeChange: (mode: QueryMode) => void
  onSubmit: (name: string, artist: string) => void
  disabled?: boolean
}

const MODE_LABELS: { value: QueryMode; label: string }[] = [
  { value: 'song', label: '歌曲' },
  { value: 'artist', label: '歌手' },
  { value: 'track_artist', label: '歌曲+歌手' },
]

export function SearchForm({ mode, onModeChange, onSubmit, disabled }: SearchFormProps) {
  const [name, setName] = useState('')
  const [artist, setArtist] = useState('')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit(name.trim(), artist.trim())
  }

  const showTrack = mode !== 'artist'
  const showArtist = mode !== 'song'
  const buttonLabel = mode === 'artist' ? '搜索歌手' : '搜索歌曲'

  return (
    <form onSubmit={handleSubmit} data-mode={mode} className="search-form">
      <div className="query-mode" role="radiogroup" aria-label="推荐查询方式">
        {MODE_LABELS.map((item) => (
          <label key={item.value}>
            <input
              type="radio"
              name="query-mode"
              value={item.value}
              checked={mode === item.value}
              onChange={() => onModeChange(item.value)}
            />
            <span>{item.label}</span>
          </label>
        ))}
      </div>

      {showTrack && (
        <div className="query-field">
          <label htmlFor="track-name">歌曲</label>
          <div className="input-wrap">
            <span aria-hidden="true">⌕</span>
            <input
              id="track-name"
              placeholder="小幸运"
              autoComplete="off"
              required
              disabled={disabled}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
        </div>
      )}

      {showArtist && (
        <div className="query-field">
          <label htmlFor="artist-name">
            艺人 <small>{mode === 'artist' ? '支持中英文与别名' : '可选，可缩小范围'}</small>
          </label>
          <div className="input-wrap">
            <span aria-hidden="true">♪</span>
            <input
              id="artist-name"
              placeholder="周杰伦 / Jay Chou"
              autoComplete="off"
              required={mode === 'artist'}
              disabled={disabled}
              value={artist}
              onChange={(event) => setArtist(event.target.value)}
            />
          </div>
        </div>
      )}

      <button className="primary-button" type="submit" disabled={disabled}>
        {buttonLabel}
      </button>
    </form>
  )
}