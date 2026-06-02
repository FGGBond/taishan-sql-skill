from __future__ import annotations

import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import __version__
from .config import MAX_TRACK_QUERY_BYTES, Settings, load_settings
from .device_id import get_device_id
from .http_util import ssl_context
from .user_info import get_user_erp


def track_api_call(spec_name: str, params: dict[str, Any] | None, settings: Settings | None = None) -> None:
    """Fire-and-forget usage tracking before Taishan API calls. Never raises."""
    settings = settings or load_settings()
    if not settings.tracking_enabled:
        return

    endpoint = settings.tracking_endpoint
    if not endpoint:
        return

    environment = str((params or {}).get("environment") or (params or {}).get("env") or "prod")
    properties: dict[str, Any] = {
        "device_id": get_device_id(),
        "spec": spec_name,
        "cli_version": __version__,
        "environment": environment,
    }
    erp = get_user_erp(settings, environment)
    if erp:
        properties["erp"] = erp

    try:
        _send_track_event(
            endpoint=endpoint,
            event_name=f"api_{spec_name}",
            properties=properties,
            timeout_seconds=settings.tracking_timeout_seconds,
        )
    except Exception:
        return


def _send_track_event(
    *,
    endpoint: str,
    event_name: str,
    properties: dict[str, Any],
    timeout_seconds: float,
) -> bool:
    """Send log fields as URL query params via GET (Aliyun SLS WebTracking API 0.6.0)."""
    params: dict[str, Any] = {
        "APIVersion": "0.6.0",
        "__topic__": "user_behavior",
        "event": event_name,
        "timestamp": int(time.time()),
    }
    params.update(properties)

    query = urlencode(params)
    if len(query.encode("utf-8")) >= MAX_TRACK_QUERY_BYTES:
        return False

    url = f"{endpoint}?{query}"
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds, context=ssl_context()) as response:
            status = getattr(response, "status", response.getcode())
            return status == 200
    except URLError:
        return False
