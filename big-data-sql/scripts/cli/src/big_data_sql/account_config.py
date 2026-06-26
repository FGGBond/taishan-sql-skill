from __future__ import annotations

import os
import sys
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


def extract_queues(api_result: dict[str, Any]) -> list[dict[str, Any]]:
    return _api_list_items(api_result)


def linux_user_from_market(market: dict[str, Any]) -> str:
    return str(
        market.get("marketUser") or market.get("linuxUser") or market.get("marketCode") or ""
    ).strip()


def production_accounts(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in accounts
        if item.get("type") == _PRODUCTION_ACCOUNT_TYPE and str(item.get("code") or "").strip()
    ]


def build_run_config(
    *,
    linux_user: str,
    market: dict[str, Any],
    account: dict[str, Any],
    queue: dict[str, Any],
) -> dict[str, str]:
    account_code = str(account.get("code") or "")
    queue_code = str(queue.get("queueCode") or "")
    business_line = str(queue.get("businessLine") or "")
    cluster_code = str(
        queue.get("logicComputeClusterCode") or queue.get("clusterCode") or "cairne"
    )
    market_code = str(market.get("marketCode") or linux_user)
    return {
        "market_linux_user": linux_user,
        "market_code": market_code,
        "account_code": account_code,
        "queue_code": queue_code,
        "business_line": business_line,
        "cluster_code": cluster_code,
        "market_name": str(market.get("marketName") or market_code),
        "account_name": str(account.get("name") or account_code),
        "queue_name": str(queue.get("queueName") or queue_code),
    }


def build_target_entry(
    *,
    index: int,
    market: dict[str, Any],
    account: dict[str, Any],
    queue: dict[str, Any],
) -> dict[str, Any]:
    linux_user = linux_user_from_market(market)
    run_config = build_run_config(
        linux_user=linux_user,
        market=market,
        account=account,
        queue=queue,
    )
    label = (
        f"{run_config['market_name']} / {run_config['account_name']} / {run_config['queue_name']}"
    )
    return {
        "index": index,
        "label": label,
        **run_config,
    }


def list_run_targets(settings: Settings | None = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Enumerate all runnable market / production account / queue combinations for current ERP."""
    settings = settings or load_settings()
    from .client import PlatformClient

    client = PlatformClient(settings)
    markets_resp = client.get_markets_by_erp()
    markets = extract_markets(markets_resp)
    if not markets:
        message = str(markets_resp.get("message") or "无法获取 ERP 可用集市列表")
        return [], failure("MARKET_UNAVAILABLE", message, next_action="doctor")

    targets: list[dict[str, Any]] = []
    index = 1
    for market in markets:
        linux_user = linux_user_from_market(market)
        if not linux_user:
            continue
        accounts_resp = client.get_accounts_by_erp(linux_user)
        accounts = production_accounts(extract_accounts(accounts_resp))
        for account in accounts:
            account_code = str(account.get("code") or "")
            queues_resp = client.get_queues_by_erp(linux_user, account_code)
            queues = extract_queues(queues_resp)
            for queue in queues:
                if not queue.get("queueCode"):
                    continue
                targets.append(
                    build_target_entry(index=index, market=market, account=account, queue=queue)
                )
                index += 1

    if not targets:
        return [], failure(
            "TARGET_UNAVAILABLE",
            "未找到可用的生产账号与队列组合，请确认 dp.jd.com 权限或联系管理员。",
            next_action="doctor",
        )
    return targets, None


def target_selection_failure(targets: list[dict[str, Any]], *, message: str | None = None) -> dict[str, Any]:
    return failure(
        "TARGET_SELECTION_REQUIRED",
        message
        or "检测到多个可用的大数据账号/队列，请让用户选择后使用 --target-index 或 --account-code 重新执行。",
        recoverable=True,
        choices=_choices_for_display(targets),
        next_action="list-targets",
        hint="bash scripts/big-data-sql list-targets",
    )


def _choices_for_display(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": item["index"],
            "label": item["label"],
            "market_linux_user": item["market_linux_user"],
            "market_name": item["market_name"],
            "account_code": item["account_code"],
            "account_name": item["account_name"],
            "queue_code": item["queue_code"],
            "queue_name": item["queue_name"],
        }
        for item in targets
    ]


def select_target(
    targets: list[dict[str, Any]],
    *,
    target_index: int | None = None,
    account_code: str | None = None,
    queue_code: str | None = None,
    saved: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if account_code:
        matches = [
            t
            for t in targets
            if t["account_code"] == account_code
            and (not queue_code or t["queue_code"] == queue_code)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1 and queue_code:
            return None

    if target_index is not None:
        for item in targets:
            if item["index"] == target_index:
                return item
        return None

    if saved:
        saved_account = str(saved.get("account_code") or "")
        saved_queue = str(saved.get("queue_code") or "")
        if saved_account and saved_queue:
            matches = [
                t
                for t in targets
                if t["account_code"] == saved_account and t["queue_code"] == saved_queue
            ]
            if len(matches) == 1:
                return item_with_saved_index(matches[0], saved)

    if len(targets) == 1:
        return targets[0]
    return None


def item_with_saved_index(target: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    saved_index = saved.get("target_index")
    if saved_index is not None:
        return {**target, "target_index": saved_index}
    return target


def prompt_target_index(targets: list[dict[str, Any]]) -> int | None:
    """Interactive selection when stdin is a TTY."""
    if not sys.stdin.isatty():
        return None
    print("请选择要使用的集市 / 生产账号 / 队列：", file=sys.stderr)
    for item in targets:
        print(f"  [{item['index']}] {item['label']}", file=sys.stderr)
        print(
            f"      account={item['account_code']}  queue={item['queue_code']}",
            file=sys.stderr,
        )
    try:
        raw = input("输入序号: ").strip()
        return int(raw)
    except (EOFError, KeyboardInterrupt, ValueError):
        return None


def resolve_run_config(
    settings: Settings | None = None,
    *,
    use_saved_profile: bool = True,
    target_index: int | None = None,
    account_code: str | None = None,
    queue_code: str | None = None,
    allow_prompt: bool = True,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """
    Resolve run target: env > explicit selection > saved profile > single auto > prompt / fail.
    """
    settings = settings or load_settings()

    if _env_run_config_complete():
        return _run_config_from_env(), None

    saved: dict[str, Any] = {}
    if use_saved_profile:
        from .profile_store import load_saved_profile

        saved = load_saved_profile() or {}
        if _run_config_complete_dict(_run_config_from_profile(saved)) and not (
            target_index or account_code
        ):
            targets, err = list_run_targets(settings)
            if err:
                return None, err
            matched = select_target(targets, saved=saved)
            if matched:
                return _run_config_from_target(matched), None

    linux_user = (
        os.getenv("BDP_SQL_MARKET_LINUX_USER", "").strip()
        or os.getenv("BDP_SQL_MARKET_CODE", "").strip()
    )
    if linux_user and (account_code or os.getenv("BDP_SQL_ACCOUNT_CODE")):
        ac = account_code or os.getenv("BDP_SQL_ACCOUNT_CODE", "").strip()
        qc = queue_code or os.getenv("BDP_SQL_QUEUE_CODE", "").strip()
        targets, err = list_run_targets(settings)
        if err:
            return None, err
        picked = select_target(targets, account_code=ac, queue_code=qc or None)
        if picked:
            return _run_config_from_target(picked), None

    targets, err = list_run_targets(settings)
    if err:
        return None, err

    picked = select_target(
        targets,
        target_index=target_index,
        account_code=account_code,
        queue_code=queue_code,
        saved=saved if use_saved_profile else None,
    )

    if picked is None and allow_prompt and not (target_index or account_code):
        prompted = prompt_target_index(targets)
        if prompted is not None:
            picked = select_target(targets, target_index=prompted)

    if picked is None:
        if len(targets) == 1:
            picked = targets[0]
        else:
            return None, target_selection_failure(targets)

    return _run_config_from_target(picked), None


def resolve_run_config_for_init(
    settings: Settings | None = None,
    *,
    use_saved_profile: bool = True,
    target_index: int | None = None,
    account_code: str | None = None,
    queue_code: str | None = None,
    allow_prompt: bool = True,
) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    return resolve_run_config(
        settings,
        use_saved_profile=use_saved_profile,
        target_index=target_index,
        account_code=account_code,
        queue_code=queue_code,
        allow_prompt=allow_prompt,
    )


def _run_config_from_target(target: dict[str, Any]) -> dict[str, str]:
    return {
        "market_linux_user": str(target["market_linux_user"]),
        "market_code": str(target["market_code"]),
        "account_code": str(target["account_code"]),
        "queue_code": str(target["queue_code"]),
        "business_line": str(target["business_line"]),
        "cluster_code": str(target["cluster_code"]),
        "market_name": str(target.get("market_name") or ""),
        "account_name": str(target.get("account_name") or ""),
        "queue_name": str(target.get("queue_name") or ""),
        "target_index": str(target.get("index") or target.get("target_index") or ""),
    }


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
