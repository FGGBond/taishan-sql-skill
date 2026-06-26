import unittest

from big_data_sql.account_config import (
    build_run_config,
    extract_accounts,
    extract_markets,
    linux_user_from_market,
    production_accounts,
    select_target,
    target_selection_failure,
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

    def test_production_accounts_filters_personal(self) -> None:
        accounts = [
            {"code": "chenbinbin.51", "type": 4, "name": "陈斌斌"},
            {"code": "mart_tc_jddj_ks_algo", "type": 1, "name": "同城快送算法"},
        ]
        prod = production_accounts(accounts)
        self.assertEqual(len(prod), 1)
        self.assertEqual(prod[0]["code"], "mart_tc_jddj_ks_algo")

    def test_build_run_config(self) -> None:
        cfg = build_run_config(
            linux_user="mart_tc",
            market={"marketCode": "mart_tc", "marketName": "同城集市"},
            account={"code": "mart_tc_jddj_ks_product", "name": "产研"},
            queue={
                "queueCode": "root.mart_tc.mart_tc_jddj.mart_tc_jddj_query",
                "businessLine": "mart_tc_jddj",
                "logicComputeClusterCode": "cairne",
                "queueName": "普通生产队列",
            },
        )
        self.assertEqual(cfg["market_linux_user"], "mart_tc")
        self.assertEqual(cfg["market_name"], "同城集市")
        self.assertEqual(cfg["account_code"], "mart_tc_jddj_ks_product")

    def test_select_target_by_index(self) -> None:
        targets = [
            {"index": 1, "account_code": "a1", "queue_code": "q1"},
            {"index": 2, "account_code": "a2", "queue_code": "q2"},
        ]
        picked = select_target(targets, target_index=2)
        assert picked is not None
        self.assertEqual(picked["account_code"], "a2")

    def test_select_target_single_auto(self) -> None:
        targets = [{"index": 1, "account_code": "only", "queue_code": "q"}]
        picked = select_target(targets)
        assert picked is not None
        self.assertEqual(picked["account_code"], "only")

    def test_select_target_multiple_requires_choice(self) -> None:
        targets = [
            {"index": 1, "account_code": "a1", "queue_code": "q1"},
            {"index": 2, "account_code": "a2", "queue_code": "q2"},
        ]
        self.assertIsNone(select_target(targets))

    def test_select_target_saved_profile(self) -> None:
        targets = [
            {"index": 1, "account_code": "a1", "queue_code": "q1"},
            {"index": 2, "account_code": "a2", "queue_code": "q2"},
        ]
        picked = select_target(
            targets, saved={"account_code": "a2", "queue_code": "q2", "target_index": 2}
        )
        assert picked is not None
        self.assertEqual(picked["account_code"], "a2")

    def test_target_selection_failure_has_choices(self) -> None:
        targets = [
            {
                "index": 1,
                "label": "mart_sc / acc / queue",
                "market_linux_user": "mart_sc",
                "market_name": "零售",
                "account_code": "acc_sc",
                "account_name": "acc",
                "queue_code": "q_sc",
                "queue_name": "queue",
            }
        ]
        err = target_selection_failure(targets)
        self.assertEqual(err["error_code"], "TARGET_SELECTION_REQUIRED")
        self.assertIn("choices", err)

    def test_extract_markets_and_linux_user(self) -> None:
        markets = extract_markets(
            {
                "success": True,
                "obj": [{"marketCode": "mart_tc", "marketUser": "mart_tc"}],
            }
        )
        self.assertEqual(len(markets), 1)
        self.assertEqual(linux_user_from_market(markets[0]), "mart_tc")


if __name__ == "__main__":
    unittest.main()
