import unittest

from taishan_sql.sql_guard import is_dql


class SqlGuardTests(unittest.TestCase):
    def test_select_allowed(self) -> None:
        ok, _ = is_dql("SELECT 1")
        self.assertTrue(ok)

    def test_with_select_allowed(self) -> None:
        ok, _ = is_dql("WITH t AS (SELECT 1 AS n) SELECT n FROM t")
        self.assertTrue(ok)

    def test_delete_rejected(self) -> None:
        ok, message = is_dql("DELETE FROM users WHERE id = 1")
        self.assertFalse(ok)
        self.assertIn("DELETE", message)

    def test_insert_rejected(self) -> None:
        ok, _ = is_dql("INSERT INTO t VALUES (1)")
        self.assertFalse(ok)

    def test_select_with_trailing_dml_rejected(self) -> None:
        ok, _ = is_dql("SELECT 1; DROP TABLE t")
        self.assertFalse(ok)

    def test_forbidden_keyword_inside_comment_ignored(self) -> None:
        ok, _ = is_dql("SELECT 1 -- DELETE FROM t")
        self.assertTrue(ok)

    def test_show_allowed(self) -> None:
        ok, _ = is_dql("SHOW TABLES")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
