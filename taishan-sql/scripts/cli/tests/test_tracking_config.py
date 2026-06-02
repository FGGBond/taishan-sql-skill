import unittest

from taishan_sql.config import build_tracking_endpoint, normalize_track_host


class TrackingConfigTests(unittest.TestCase):
    def test_build_endpoint_with_host(self) -> None:
        url = build_tracking_endpoint("taishan-sql", "cn-hangzhou.log.aliyuncs.com", "taishan-logstore")
        self.assertEqual(
            url,
            "https://taishan-sql.cn-hangzhou.log.aliyuncs.com/logstores/taishan-logstore/track",
        )

    def test_normalize_region_id(self) -> None:
        self.assertEqual(normalize_track_host("cn-hangzhou"), "cn-hangzhou.log.aliyuncs.com")

    def test_normalize_full_host(self) -> None:
        self.assertEqual(
            normalize_track_host("cn-hangzhou.log.aliyuncs.com"),
            "cn-hangzhou.log.aliyuncs.com",
        )


if __name__ == "__main__":
    unittest.main()
