from __future__ import annotations

from typing import Any

from .config import Settings, load_settings

_erp_cache: dict[str, str] = {}


def extract_erp(api_result: dict[str, Any]) -> str | None:
    if not api_result.get("ok"):
        return None
    result = api_result.get("data", {}).get("result")
    if isinstance(result, dict):
        erp = result.get("erp")
        if erp:
            return str(erp)
    return None


def get_user_erp(settings: Settings | None = None, environment: str = "prod") -> str | None:
    """Return cached ERP for the current browser session, or None if unavailable."""
    settings = settings or load_settings()
    cache_key = environment
    if cache_key in _erp_cache:
        return _erp_cache[cache_key]

    from .client import TaishanClient

    result = TaishanClient(settings).call(
        "get_user_info",
        {"environment": environment},
        track=False,
    )
    erp = extract_erp(result)
    if erp:
        _erp_cache[cache_key] = erp
    return erp
