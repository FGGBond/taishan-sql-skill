import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from taishan_sql import session_store


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session_path = Path(self.temp_dir.name) / "auth-session.json"
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "TAISHAN_SQL_SESSION_PATH": str(self.session_path),
                "TAISHAN_SQL_COOKIE_CACHE": "1",
                "TAISHAN_SQL_COOKIE_CACHE_TTL": "3600",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_save_and_load_session(self) -> None:
        session_store.save_session(
            browsers=("edge", "chrome"),
            cookie_domains=("dbsv5api.jd.com",),
            browser="edge",
            cookie_header="ticket=abc",
            cookie_count=1,
        )
        loaded = session_store.load_session(
            browsers=("edge", "chrome"),
            cookie_domains=("dbsv5api.jd.com",),
        )
        assert loaded is not None
        self.assertEqual(loaded["cookie_header"], "ticket=abc")

    def test_expired_session_is_ignored(self) -> None:
        session_store.save_session(
            browsers=("edge",),
            cookie_domains=("dbsv5api.jd.com",),
            browser="edge",
            cookie_header="ticket=1",
            cookie_count=1,
        )
        data = session_store.load_session(
            browsers=("edge",),
            cookie_domains=("dbsv5api.jd.com",),
        )
        assert data is not None
        data["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        self.session_path.write_text(__import__("json").dumps(data), encoding="utf-8")
        self.assertIsNone(
            session_store.load_session(
                browsers=("edge",),
                cookie_domains=("dbsv5api.jd.com",),
            )
        )


if __name__ == "__main__":
    unittest.main()
