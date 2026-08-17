import shutil
import sqlite3
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

from app_database import AppDatabase


def read_database_files(data_dir: Path) -> bytes:
    chunks = []
    for path in list(data_dir.glob("embeat.db*")):
        try:
            chunks.append(path.read_bytes())
        except FileNotFoundError:
            pass
    return b"".join(chunks)


@contextmanager
def temporary_database_root():
    root = Path(tempfile.mkdtemp())
    try:
        yield root
    finally:
        for attempt in range(8):
            try:
                shutil.rmtree(root)
                break
            except FileNotFoundError:
                break
            except OSError as exc:
                if getattr(exc, "winerror", None) != 145 or attempt == 7:
                    raise
                time.sleep(0.025 * (attempt + 1))


class AppDatabaseTests(unittest.TestCase):
    def test_connections_are_closed_after_database_operations(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            original_connect = db._connect
            opened = []

            def tracked_connect():
                connection = original_connect()
                opened.append(connection)
                return connection

            db._connect = tracked_connect
            user_id = db.create_user("closer", "password-123")["id"]
            db.get_preferences(user_id)
            db.add_history(user_id, "search", "connection test")

            self.assertGreaterEqual(len(opened), 3)
            for connection in opened:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute("SELECT 1")

    def test_auth_sessions_and_encrypted_credentials(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            user = db.create_user("Alice", "correct horse battery")
            self.assertIsNone(db.authenticate("Alice", "wrong-password"))
            self.assertEqual(db.authenticate("alice", "correct horse battery")["id"], user["id"])
            token = db.create_session(user["id"])
            self.assertEqual(db.get_user_by_session(token)["username"], "Alice")
            db.save_credential(user["id"], "netease", {"api_url": "https://example.test", "cookie": "MUSIC_U=secret", "phone": "13800000000"})
            stored = db.get_credential(user["id"], "netease")
            self.assertEqual(stored["cookie"], "MUSIC_U=secret")
            self.assertEqual(stored["phone"], "13800000000")
            database_bytes = read_database_files(root / "data")
            self.assertNotIn(b"MUSIC_U=secret", database_bytes)
            db.save_credential(user["id"], "kugou", {"api_url": "https://example.test", "cookie": "token=secret-token; userid=42", "token": "secret-token", "userid": "42"})
            database_bytes = read_database_files(root / "data")
            self.assertNotIn(b"secret-token", database_bytes)

    def test_history_is_scoped(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            alice = db.create_user("alice", "password-123")["id"]
            bob = db.create_user("bob", "password-123")["id"]
            db.add_history(alice, "search", "Alice search", {"count": 1})
            db.add_history(bob, "search", "Bob search", {"count": 1})
            self.assertEqual(db.list_history(alice)["items"][0]["title"], "Alice search")

    def test_user_preferences_are_migrated_and_scoped(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            user_id = db.create_user("listener", "password-123")["id"]
            self.assertEqual(db.get_preferences(user_id), {"theme": None, "accent_hue": None})
            self.assertEqual(db.update_preferences(user_id, theme="berry", accent_hue=287), {"theme": "berry", "accent_hue": 287})
            self.assertEqual(db.get_preferences(user_id), {"theme": "berry", "accent_hue": 287})
            with self.assertRaises(ValueError):
                db.update_preferences(user_id, theme="unknown")

    def test_recoverable_history_round_trip(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            user_id = db.create_user("listener", "password-123")["id"]
            seed = {"track_id": "seed-1", "track_name": "Seed", "artist_name": "Artist"}
            tracks = [{"track_id": "result-1", "track_name": "Result", "artist_name": "Artist"}]
            db.add_history(user_id, "recommend", "Seed - Artist", {"seed": seed, "elapsed_ms": 12}, tracks)
            item = db.list_history(user_id)["items"][0]
            self.assertEqual(item["summary"]["seed"]["track_id"], "seed-1")
            self.assertEqual(item["tracks"][0]["track_id"], "result-1")

    def test_device_pairing_flow(self):
        with temporary_database_root() as root:
            db = AppDatabase(root)
            local = db.ensure_local_user()
            self.assertEqual(db.ensure_local_user()["id"], local["id"])
            token = db.create_device_token(local["id"])
            self.assertEqual(db.get_user_by_device(token)["username"], "local")
            self.assertIsNone(db.get_user_by_device("not-a-real-token"))
            db.save_credential(local["id"], "netease", {"api_url": "https://example.test", "cookie": "MUSIC_U=secret"})
            self.assertEqual(db.get_credential(local["id"], "netease")["cookie"], "MUSIC_U=secret")
            db.delete_device_token(token)
            self.assertIsNone(db.get_user_by_device(token))


if __name__ == "__main__":
    unittest.main()
