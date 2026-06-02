import unittest

from taishan_sql.user_info import extract_erp


class UserInfoTests(unittest.TestCase):
    def test_extract_erp_success(self) -> None:
        result = {
            "ok": True,
            "data": {
                "result": {
                    "erp": "zhukai.129",
                    "organizationName": "订运单研发组",
                }
            },
        }
        self.assertEqual(extract_erp(result), "zhukai.129")

    def test_extract_erp_missing(self) -> None:
        self.assertIsNone(extract_erp({"ok": False}))
        self.assertIsNone(extract_erp({"ok": True, "data": {"result": {}}}))


if __name__ == "__main__":
    unittest.main()
