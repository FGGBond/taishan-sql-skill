import unittest
from http.cookiejar import Cookie, CookieJar

from big_data_sql.auth import (
    _build_cookie_header,
    _cached_header_stale,
    _matches_domain,
    cookie_value_from_header,
)


class MatchesDomainTests(unittest.TestCase):
    def test_host_only_dp(self) -> None:
        domains = ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com")
        self.assertTrue(_matches_domain("dp.jd.com", domains))

    def test_excludes_unrelated_jd_subdomain(self) -> None:
        domains = ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com")
        self.assertFalse(_matches_domain("xingyun.jd.com", domains))

    def test_parent_domain_cookie(self) -> None:
        domains = ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com")
        self.assertTrue(_matches_domain(".jd.com", domains))


class BuildCookieHeaderTests(unittest.TestCase):
    def _jar_with(self, *cookies: Cookie) -> CookieJar:
        jar = CookieJar()
        for cookie in cookies:
            jar.set_cookie(cookie)
        return jar

    def test_domain_priority_for_jsessionid(self) -> None:
        jar = self._jar_with(
            Cookie(
                version=0,
                name="JSESSIONID",
                value="wrong-from-xingyun",
                port=None,
                port_specified=False,
                domain="xingyun.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
            Cookie(
                version=0,
                name="JSESSIONID",
                value="correct-from-dp",
                port=None,
                port_specified=False,
                domain="dp.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
        )
        header = _build_cookie_header(
            jar,
            ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com"),
        )
        self.assertIn("JSESSIONID=correct-from-dp", header)
        self.assertNotIn("wrong-from-xingyun", header)

    def test_scriptcenter_ssa_bdp_wins_over_dp(self) -> None:
        jar = self._jar_with(
            Cookie(
                version=0,
                name="ssa.bdp",
                value="old-on-dp",
                port=None,
                port_specified=False,
                domain="dp.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
            Cookie(
                version=0,
                name="ssa.bdp",
                value="new-on-scriptcenter",
                port=None,
                port_specified=False,
                domain="scriptcenter.dp.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
        )
        header = _build_cookie_header(
            jar,
            ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com"),
        )
        self.assertEqual(cookie_value_from_header(header, "ssa.bdp"), "new-on-scriptcenter")

    def test_skips_empty_values(self) -> None:
        jar = self._jar_with(
            Cookie(
                version=0,
                name="ssa.bdp",
                value="",
                port=None,
                port_specified=False,
                domain="scriptcenter.dp.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
            Cookie(
                version=0,
                name="ssa.bdp",
                value="fallback-dp",
                port=None,
                port_specified=False,
                domain="dp.jd.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            ),
        )
        header = _build_cookie_header(
            jar,
            ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com"),
        )
        self.assertEqual(cookie_value_from_header(header, "ssa.bdp"), "fallback-dp")


class CachedHeaderStaleTests(unittest.TestCase):
    def test_detects_ssa_bdp_mismatch(self) -> None:
        from unittest.mock import MagicMock, patch

        settings = MagicMock()
        settings.browsers = ("chrome",)
        settings.cookie_domains = ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com")

        with patch(
            "big_data_sql.auth._read_browser_cookie_header",
            return_value="ssa.bdp=new-value",
        ):
            self.assertTrue(_cached_header_stale(settings, "ssa.bdp=old-value"))

        with patch(
            "big_data_sql.auth._read_browser_cookie_header",
            return_value="ssa.bdp=same-value",
        ):
            self.assertFalse(_cached_header_stale(settings, "ssa.bdp=same-value"))


if __name__ == "__main__":
    unittest.main()
