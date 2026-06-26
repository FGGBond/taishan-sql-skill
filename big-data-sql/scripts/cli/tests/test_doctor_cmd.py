import unittest
from unittest.mock import MagicMock, patch

from big_data_sql.doctor_cmd import (
    doctor_verdict,
    probe_platform_apis,
    run_doctor,
    summarize_api_check,
)


class SummarizeApiCheckTests(unittest.TestCase):
    def test_login_user_success(self) -> None:
        check = summarize_api_check(
            "loginUser",
            "/request/portal/common/loginUser",
            {"success": True, "obj": {"erp": "zhukai.129"}},
        )
        self.assertTrue(check["ok"])
        self.assertEqual(check["erp"], "zhukai.129")

    def test_login_user_http_error(self) -> None:
        check = summarize_api_check(
            "loginUser",
            "/request/portal/common/loginUser",
            {"error_code": "HTTP_ERROR", "message": "HTTP 401: Unauthorized", "status": 401},
        )
        self.assertFalse(check["ok"])
        self.assertEqual(check["status"], 401)

    def test_get_market_by_erp_success(self) -> None:
        check = summarize_api_check(
            "getMarketByErp",
            "/scriptcenter/config/getMarketByErp.ajax",
            {"success": True, "obj": [{"marketCode": "mart_a"}]},
        )
        self.assertTrue(check["ok"])
        self.assertEqual(check["market_count"], 1)

    def test_get_erp_local_project_missing(self) -> None:
        check = summarize_api_check(
            "getErpLocalProject",
            "/scriptcenter/project/getErpLocalProject.ajax",
            {"error_code": "HTTP_ERROR", "message": "HTTP 401: Unauthorized", "status": 401},
        )
        self.assertFalse(check["ok"])


class DoctorVerdictTests(unittest.TestCase):
    def test_all_ok(self) -> None:
        ok, code, _ = doctor_verdict(
            [
                {"name": "loginUser", "ok": True},
                {"name": "getErpLocalProject", "ok": True},
                {"name": "getMarketByErp", "ok": True},
            ]
        )
        self.assertTrue(ok)
        self.assertIsNone(code)

    def test_script_center_failure(self) -> None:
        ok, code, message = doctor_verdict(
            [
                {"name": "loginUser", "ok": True, "erp": "user.1"},
                {
                    "name": "getMarketByErp",
                    "ok": False,
                    "message": "HTTP 401: Unauthorized",
                },
            ]
        )
        self.assertFalse(ok)
        self.assertEqual(code, "SCRIPT_CENTER_UNAVAILABLE")
        self.assertIn("getMarketByErp", message)

    def test_login_user_failure(self) -> None:
        ok, code, _ = doctor_verdict(
            [
                {"name": "loginUser", "ok": False, "message": "HTTP 401: Unauthorized"},
            ]
        )
        self.assertFalse(ok)
        self.assertEqual(code, "AUTH_UNAVAILABLE")


class RunDoctorTests(unittest.TestCase):
    @patch("big_data_sql.doctor_cmd.load_browser_cookies")
    @patch("big_data_sql.doctor_cmd.PlatformClient")
    def test_run_doctor_reports_failed_script_center_apis(
        self,
        client_cls: MagicMock,
        load_cookies: MagicMock,
    ) -> None:
        load_cookies.return_value = MagicMock(
            browser="chrome",
            domains=("dp.jd.com",),
            cookie_header="a=b",
            cookie_count=1,
            source="browser",
        )
        client = client_cls.return_value
        client.get_login_user.return_value = {
            "success": True,
            "obj": {"erp": "shenwenjiang.1"},
        }
        client.get_erp_local_project.return_value = {
            "error_code": "HTTP_ERROR",
            "message": "HTTP 401: Unauthorized",
            "status": 401,
        }
        client.get_markets_by_erp.return_value = {
            "error_code": "HTTP_ERROR",
            "message": "HTTP 401: Unauthorized",
            "status": 401,
        }

        result = run_doctor(public_settings={})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "SCRIPT_CENTER_UNAVAILABLE")
        self.assertEqual(
            sorted(result["failed_apis"]),
            ["getErpLocalProject", "getMarketByErp"],
        )
        self.assertEqual(len(result["api_checks"]), 3)
        self.assertFalse(result["api_checks"][1]["ok"])
        self.assertFalse(result["api_checks"][2]["ok"])


class ProbePlatformApisTests(unittest.TestCase):
    def test_probe_calls_all_endpoints(self) -> None:
        client = MagicMock()
        client.get_login_user.return_value = {"success": True, "obj": {"erp": "a.b"}}
        client.get_erp_local_project.return_value = {
            "success": True,
            "obj": {"gitProjectId": "123"},
        }
        client.get_markets_by_erp.return_value = {"success": True, "obj": []}

        checks = probe_platform_apis(client)

        self.assertEqual(len(checks), 3)
        self.assertTrue(all(check["ok"] for check in checks))
        client.get_login_user.assert_called_once()
        client.get_erp_local_project.assert_called_once()
        client.get_markets_by_erp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
