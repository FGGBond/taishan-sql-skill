import unittest

from big_data_sql.user_info import extract_erp


class UserInfoTests(unittest.TestCase):
    def test_extract_erp_success(self) -> None:
        result = {
            "success": True,
            "code": 0,
            "obj": {"erp": "zhukai.129", "name": "朱恺"},
        }
        self.assertEqual(extract_erp(result), "zhukai.129")

    def test_extract_erp_failure_envelope(self) -> None:
        self.assertIsNone(extract_erp({"error_code": "AUTH_UNAVAILABLE"}))
        self.assertIsNone(extract_erp({"success": False, "obj": {}}))


if __name__ == "__main__":
    unittest.main()
