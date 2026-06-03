from __future__ import annotations

from typing import Any

from .config import Settings, load_settings

_erp_cache: str | None = None


def extract_erp(api_result: dict[str, Any]) -> str | None:
    if api_result.get("error_code"):
        return None
    if api_result.get("success") is True:
        obj = api_result.get("obj")
        if isinstance(obj, dict):
            erp = obj.get("erp")
            if erp:
                return str(erp)
    return None


def get_user_erp(settings: Settings | None = None) -> str | None:
    """Return cached ERP for the current browser session, or None if unavailable."""
    global _erp_cache
    if _erp_cache:
        return _erp_cache

    from .client import PlatformClient

    result = PlatformClient(settings).get_login_user(track=False)
    erp = extract_erp(result)
    if erp:
        _erp_cache = erp
    return erp
