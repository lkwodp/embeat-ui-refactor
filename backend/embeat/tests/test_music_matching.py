import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from artist_aliases import (
    build_artist_alias_maps,
    choose_musicbrainz_chinese_name,
    load_curated_aliases,
    load_musicbrainz_aliases,
    merge_artist_alias_sources,
)
from music_matching import artist_search_aliases, track_title_aliases
from service import EmbeatService


class MatchingRegressionTests(unittest.TestCase):
    def test_korean_artist_aliases_are_case_insensitive(self):
        aliases = {item.casefold() for item in artist_search_aliases("ha yea song")}
        self.assertIn("송하예", aliases)
        self.assertIn("宋荷艺", aliases)

    def test_korean_title_aliases(self):
        titles = {item.casefold() for item in track_title_aliases(["Your Regards"], ["Ha Yea Song"])}
        self.assertIn("니 소식", titles)


class ArtistAliasTests(unittest.TestCase):
    def test_musicbrainz_prefers_simplified_chinese(self):
        aliases = json.dumps([
            {"name": "漢斯·季默", "locale": "zh", "primary": True},
            {"name": "汉斯·季默", "locale": "zh-Hans-CN", "primary": True},
        ], ensure_ascii=False)
        self.assertEqual(
            choose_musicbrainz_chinese_name("Hans Zimmer", "", aliases),
            "汉斯·季默",
        )

    def test_musicbrainz_filters_kana_and_bracket_labels(self):
        self.assertIsNone(
            choose_musicbrainz_chinese_name("Relax alpha Wave", "ぐっすり眠れるα波", "[]")
        )
        self.assertIsNone(
            choose_musicbrainz_chinese_name("Nature Sounds", "[自然声音]", "[]")
        )

    def test_non_primary_alias_does_not_replace_valid_primary_name(self):
        aliases = json.dumps([
            {"name": "S.H.E", "locale": "zh", "primary": True},
            {"name": "女朋友", "locale": "zh", "primary": False},
        ], ensure_ascii=False)
        self.assertIsNone(choose_musicbrainz_chinese_name("S.H.E", "S.H.E", aliases))

    def test_curated_alias_wins_and_maps_are_case_insensitive(self):
        merged = merge_artist_alias_sources(
            ({"Hacken Lee": "李克勤", "Sodagreen": "苏打绿"},),
            ({"hacken lee": "克勤", "Hans Zimmer": "汉斯·季默"},),
        )
        english_to_chinese, chinese_to_english = build_artist_alias_maps(merged)
        self.assertEqual(english_to_chinese["hacken lee"], "李克勤")
        self.assertEqual(english_to_chinese["SODAGREEN".casefold()], "苏打绿")
        self.assertEqual(english_to_chinese["hans zimmer"], "汉斯·季默")
        self.assertEqual(chinese_to_english["李克勤"], "Hacken Lee")

    def test_json_overrides_read_only_musicbrainz_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = root / "mb_lookup.db"
            json_path = root / "aliases.json"
            with closing(sqlite3.connect(db_path)) as db:
                db.execute(
                    "CREATE TABLE lookup (artist_name TEXT, cn_artist_name TEXT, zh_aliases TEXT)"
                )
                db.executemany(
                    "INSERT INTO lookup VALUES (?, ?, ?)",
                    [
                        ("Hacken Lee", "克勤", "[]"),
                        ("Hans Zimmer", "汉斯·季默", "[]"),
                    ],
                )
                db.commit()
            json_path.write_text(
                json.dumps([{"english": "Hacken Lee", "chinese": "李克勤"}], ensure_ascii=False),
                encoding="utf-8",
            )

            curated = load_curated_aliases(json_path)
            musicbrainz = load_musicbrainz_aliases(db_path)
            merged = merge_artist_alias_sources((curated,), (musicbrainz,))

            self.assertEqual(merged["Hacken Lee"], "李克勤")
            self.assertEqual(merged["Hans Zimmer"], "汉斯·季默")


class ArtistRecommendationTests(unittest.TestCase):
    def test_track_and_artist_search_filters_unrelated_same_title(self):
        records = [
            SimpleNamespace(payload={
                "track_id": "jay-version",
                "track_name": "Sunny Day",
                "artist_name": "Jay Chou",
                "album_name": "Album A",
                "popularity": 0.7,
            }),
            SimpleNamespace(payload={
                "track_id": "other-version",
                "track_name": "Sunny Day",
                "artist_name": "Ken Chu",
                "album_name": "Album B",
                "popularity": 0.9,
            }),
        ]
        database = SimpleNamespace(
            collection_name="spotify_tracks",
            client=SimpleNamespace(scroll=lambda **_kwargs: (records, None)),
        )
        service = EmbeatService.__new__(EmbeatService)
        service._qdrant_call = lambda callback: callback(database)

        result = service.search("Sunny Day", "Jay Chou", limit=20)

        self.assertEqual([item["track_id"] for item in result], ["jay-version"])

    def test_artist_recommendation_resolves_exact_artist_and_uses_representative_track(self):
        artist_records = [
            SimpleNamespace(payload={
                "artist_idx": 41,
                "artist_name": "Jay Chou Tribute",
                "popularity": 0.9,
            }),
            SimpleNamespace(payload={
                "artist_idx": 7,
                "artist_name": "Jay Chou",
                "popularity": 0.8,
            }),
        ]
        representative = SimpleNamespace(payload={
            "track_id": "seed-track",
            "track_name": "Sunny Day",
            "artist_idx": 7,
            "artist_name": "Jay Chou",
            "album_name": "Album",
            "artist_genres": "mandopop",
            "popularity": 0.8,
        })

        class FakeDatabase:
            collection_name = "spotify_tracks"

            def __init__(self):
                self.client = SimpleNamespace(scroll=lambda **_kwargs: (artist_records, None))
                self.resolved_artist_idx = None
                self.search_track_id = None

            def find_query_record_by_artist(self, artist_idx=0, artist_name=None):
                self.resolved_artist_idx = artist_idx
                return representative

            def search_entry(self, track_id="", artist_idx=0, top_k=20):
                self.search_track_id = track_id
                return [{
                    "track_id": "result-track",
                    "track_name": "Result",
                    "artist_name": "Related Artist",
                    "album_name": "Result Album",
                    "score": 0.88,
                    "sources": ["similar"],
                }]

        database = FakeDatabase()
        service = EmbeatService.__new__(EmbeatService)
        service._qdrant_call = lambda callback: callback(database)

        result = service.recommend_artist("Jay Chou", limit=5)

        self.assertEqual(database.resolved_artist_idx, 7)
        self.assertEqual(database.search_track_id, "seed-track")
        self.assertEqual(result["mode"], "artist")
        self.assertEqual(result["artist"]["artist_name"], "Jay Chou")
        self.assertEqual(result["representative_track"]["track_id"], "seed-track")
        self.assertEqual(result["tracks"][0]["track_id"], "result-track")


if __name__ == "__main__":
    unittest.main()