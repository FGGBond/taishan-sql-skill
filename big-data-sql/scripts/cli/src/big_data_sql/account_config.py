from __future__ import annotations

import os
from typing import Any

from .config import Settings, load_settings
from .normalize import failure

_PRODUCTION_ACCOUNT_TYPE = 1


def _api_list_items(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    if api_result.get("error_code"):
        return []
    if api_result.get("success") is not True and api_result.get("code") not in (0, "0"):
        return []
    obj = api_result.get("obj")
    if not isinstance(obj, list):
        return []
    return [item for item in obj if isinstance(item, dict)]


def extract_accounts(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    return _api_list_items(api_result)


def extract_markets(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    return _api_list_items(api_result)


def pick_default_market(markets: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in markets:
        linux_user = str(item.get("marketUser") or item.get("linuxUser") or "").strip()
        if linux_user:
            return item
    return markets[0] if markets else None


def linux_user_from_market(market: dict[str, Any]) -> str:
    return str(
        market.get("marketUser") or market.get("linuxUser") or market.get("marketCode") or ""
    ).strip()


def extract_queues(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    return extract_accounts(api_result)


def pick_production_account(accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in accounts:
        if item.get("type") == _PRODUCTION_ACCOUNT_TYPE and item.get("code"):
            return item
    for item in accounts:
        code = str(item.get("code") or "")
        if code and item.get("type") != 4:
            return item
    return accounts[0] if accounts else None


def pick_default_queue(queues: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in queues:
        if item.get("queueCode"):
            return item
    return None


def infer_linux_user_from_account_code(account_code: str) -> str:
    """e.g. mart_tc_jddj_ks_product -> mart_tc"""
    if "_jddj" in account_code:
        return account_code.split("_jddj", 1)[0]
    parts = account_code.split("_")
    if len(parts) >= 2:
        return "_".join(parts[:2])
    return account_code


def build_run_config(
    *,
    linux_user: str,
    account: dict[str, Any],
    queue: dict[str, Any],
) -> dict[str, str]:
    account_code = str(account.get("code") or "")
    queue_code = str(queue.get("queueCode") or "")
    business_line = str(queue.get("businessLine") or "")
    cluster_code = str(
        queue.get("logicComputeClusterCode") or queue.get("clusterCode") or "cairne"
    )
    return {
        "market_linux_user": linux_user,
        "market_code": linux_user,
        "account_code": account_code,
        "queue_code": queue_code,
        "business_line": business_line,
        "cluster_code": cluster_code,
    }


def resolve_run_config_for_init(
    settings: Settings | None = None,
    *,
    use_saved_profile: bool = True,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """Resolve market/account/queue: env > profile > getAccountByErp4DQ + getQueueByErp."""
    settings = settings or load_settings()

    if _env_run_config_complete():
        return _run_config_from_env(), None

    if use_saved_profile:
        from .profile_store import load_saved_profile

        saved = load_saved_profile() or {}
        saved_cfg = _run_config_from_profile(saved)
        if _run_config_complete_dict(saved_cfg):
            return saved_cfg, None

    from .client import PlatformClient

    client = PlatformClient(settings)
    linux_user = (
        os.getenv("BDP_SQL_MARKET_LINUX_USER", "").strip()
        or os.getenv("BDP_SQL_MARKET_CODE", "").strip()
    )

    if not linux_user:
        markets_resp = client.get_markets_by_erp()
        markets = extract_markets(markets_resp)
        if not markets:
            message = str(markets_resp.get("message") or "无法获取 ERP 可用集市列表")
            return None, failure(
                "MARKET_UNAVAILABLE",
                message,
                next_action="doctor",
            )
        market = pick_default_market(markets)
        if not market:
            return None, failure(
                "MARKET_UNAVAILABLE",
                "未找到可用集市，请设置 BDP_SQL_MARKET_LINUX_USER。",
                next_action="doctor",
            )
        linux_user = linux_user_from_market(market)

    accounts_resp = client.get_accounts_by_erp(linux_user or None)
    accounts = extract_accounts(accounts_resp)
    if not accounts:
        message = str(accounts_resp.get("message") or "无法获取生产账号列表")
        return None, failure(
            "ACCOUNT_UNAVAILABLE",
            message,
            next_action="doctor",
            linux_user=linux_user or None,
        )

    account = pick_production_account(accounts)
    if not account:
        return None, failure(
            "ACCOUNT_UNAVAILABLE",
            "未找到可用的生产账号，请设置 BDP_SQL_ACCOUNT_CODE 或 BDP_SQL_MARKET_LINUX_USER。",
            next_action="doctor",
        )

    account_code = str(account.get("code") or "")
    if not linux_user:
        linux_user = infer_linux_user_from_account_code(account_code)

    queues_resp = client.get_queues_by_erp(linux_user, account_code)
    queues = extract_queues(queues_resp)
    if not queues:
        message = str(queues_resp.get("message") or "无法获取队列列表")
        return None, failure(
            "QUEUE_UNAVAILABLE",
            message,
            account_code=account_code,
            linux_user=linux_user,
            next_action="doctor",
        )

    queue = pick_default_queue(queues)
    if not queue:
        return None, failure(
            "QUEUE_UNAVAILABLE",
            "未找到可用队列，请设置 BDP_SQL_QUEUE_CODE。",
            next_action="doctor",
        )

    return build_run_config(linux_user=linux_user, account=account, queue=queue), None


def _env_run_config_complete() -> bool:
    return _run_config_complete_dict(_run_config_from_env())


def _run_config_from_env() -> dict[str, str]:
    return {
        "market_linux_user": os.getenv("BDP_SQL_MARKET_LINUX_USER", "").strip()
        or os.getenv("BDP_SQL_MARKET_CODE", "").strip(),
        "market_code": os.getenv("BDP_SQL_MARKET_CODE", "").strip()
        or os.getenv("BDP_SQL_MARKET_LINUX_USER", "").strip(),
        "account_code": os.getenv("BDP_SQL_ACCOUNT_CODE", "").strip(),
        "queue_code": os.getenv("BDP_SQL_QUEUE_CODE", "").strip(),
        "business_line": os.getenv("BDP_SQL_BUSINESS_LINE", "").strip(),
        "cluster_code": os.getenv("BDP_SQL_CLUSTER_CODE", "").strip(),
    }


def _run_config_from_profile(saved: dict[str, Any]) -> dict[str, str]:
    return {
        "market_linux_user": str(saved.get("market_linux_user") or ""),
        "market_code": str(saved.get("market_code") or ""),
        "account_code": str(saved.get("account_code") or ""),
        "queue_code": str(saved.get("queue_code") or ""),
        "business_line": str(saved.get("business_line") or ""),
        "cluster_code": str(saved.get("cluster_code") or ""),
    }


def _run_config_complete_dict(cfg: dict[str, str]) -> bool:
    return bool(
        cfg.get("market_linux_user")
        and cfg.get("account_code")
        and cfg.get("queue_code")
        and cfg.get("business_line")
    )
