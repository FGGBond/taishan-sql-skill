from __future__ import annotations

from typing import Any


def success(**payload: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"ok": True, "warnings": []}
    base.update(payload)
    return base


def failure(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "recoverable": error_code
        in {"AUTH_EXPIRED", "AUTH_UNAVAILABLE", "HTTP_ERROR", "TIMEOUT", "STILL_RUNNING"},
    }
    payload.update(extra)
    return payload
