"""Pydantic models for the HTTP API surface.

These mirror the shapes produced by the oss ``EmbeatService`` (``_pack_track``,
``search``, ``recommend``, ``recommend_artist``) so the two layers stay in sync.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Track(BaseModel):
    track_id: str = ""
    track_name: str = ""
    artist_name: str = ""
    track_name_zh: str = ""
    artist_name_zh: str = ""
    album_name: str = ""
    artist_genres: str = ""
    popularity: float = 0.0
    score: float = 0.0
    match_score: float | None = None
    sources: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    tracks: list[Track]


class RecommendRequest(BaseModel):
    track_id: str
    limit: int = Field(default=20, ge=1, le=50)


class RecommendMultiRequest(BaseModel):
    track_ids: list[str]
    limit: int = Field(default=50, ge=1, le=100)
    history_title: str = ""


class RecommendResponse(BaseModel):
    seed: Track | None = None
    seeds: list[Track] | None = None
    tracks: list[Track]
    elapsed_ms: int = 0


class Artist(BaseModel):
    input_name: str = ""
    artist_idx: int = 0
    artist_name: str = ""
    artist_name_zh: str = ""
    artist_genres: str = ""


class ArtistRecommendResponse(BaseModel):
    mode: str = "artist"
    artist: Artist
    representative_track: Track
    tracks: list[Track]
    elapsed_ms: int = 0


class HealthResponse(BaseModel):
    ready: bool
    points: int = 0
    service: str = "embeat-web"
