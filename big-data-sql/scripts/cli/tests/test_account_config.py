import unittest

from big_data_sql.account_config import (
    build_run_config,
    extract_accounts,
    extract_markets,
    infer_linux_user_from_account_code,
    linux_user_from_market,
    pick_default_market,
    pick_default_queue,
    pick_production_account,
)


class AccountConfigTests(unittest.TestCase):
    def test_extract_accounts(self) -> None:
        payload = {
            "success": True,
            "obj": [{"code": "mart_tc_jddj_ks_product", "type": 1}],
        }
        accounts = extract_accounts(payload)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["code"], "mart_tc_jddj_ks_product")

    def test_pick_production_account(self) -> None:
        accounts = [
            {"code": "zhukai.129", "type": 4},
            {"code": "mart_tc_jddj_ks_product", "type": 1},
        ]
        picked = pick_production_account(accounts)
        assert picked is not None
        self.assertEqual(picked["code"], "mart_tc_jddj_ks_product")

    def test_infer_linux_user(self) -> None:
        self.assertEqual(
            infer_linux_user_from_account_code("mart_tc_jddj_ks_product"),
            "mart_tc",
        )

    def test_build_run_config(self) -> None:
        cfg = build_run_config(
            linux_user="mart_tc",
            account={"code": "mart_tc_jddj_ks_product"},
            queue={
                "queueCode": "root.mart_tc.mart_tc_jddj.mart_tc_jddj_query",
                "businessLine": "mart_tc_jddj",
                "logicComputeClusterCode": "cairne",
            },
        )
        self.assertEqual(cfg["market_linux_user"], "mart_tc")
        self.assertEqual(cfg["account_code"], "mart_tc_jddj_ks_product")
        self.assertEqual(cfg["queue_code"], "root.mart_tc.mart_tc_jddj.mart_tc_jddj_query")
        self.assertEqual(cfg["business_line"], "mart_tc_jddj")
        self.assertEqual(cfg["cluster_code"], "cairne")

    def test_pick_default_queue(self) -> None:
        queues = [{"queueCode": "root.mart_tc.query"}]
        picked = pick_default_queue(queues)
        assert picked is not None
        self.assertEqual(picked["queueCode"], "root.mart_tc.query")

    def test_extract_markets_and_linux_user(self) -> None:
        markets = extract_markets(
            {
                "success": True,
                "obj": [{"marketCode": "mart_tc", "marketUser": "mart_tc"}],
            }
        )
        self.assertEqual(len(markets), 1)
        picked = pick_default_market(markets)
        assert picked is not None
        self.assertEqual(linux_user_from_market(picked), "mart_tc")


if __name__ == "__main__":
    unittest.main()
