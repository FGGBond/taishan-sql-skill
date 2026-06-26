from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_SESSION_DIR = Path.home() / ".config" / "taishan-sql"
DEFAULT_SESSION_FILE = DEFAULT_SESSION_DIR / "auth-session.json"
DEFAULT_CACHE_TTL_SECONDS = 4 * 3600


def session_path() -> Path:
    raw = os.getenv("TAISHAN_SQL_SESSION_PATH", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_SESSION_FILE


def cache_enabled() -> bool:
    raw = os.getenv("TAISHAN_SQL_COOKIE_CACHE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def cache_ttl_seconds() -> int:
    raw = os.getenv("TAISHAN_SQL_COOKIE_CACHE_TTL", str(DEFAULT_CACHE_TTL_SECONDS)).strip()
    try:
        ttl = int(raw)
    except ValueError:
        return DEFAULT_CACHE_TTL_SECONDS
    return max(60, ttl)


def settings_fingerprint(*, browsers: tuple[str, ...], cookie_domains: tuple[str, ...]) -> str:
    return f"browsers={','.join(browsers)};domains={','.join(cookie_domains)}"


def load_session(
    *,
    browsers: tuple[str, ...],
    cookie_domains: tuple[str, ...],
) -> dict[str, Any] | None:
    if not cache_enabled():
        return None

    path = session_path()
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    if data.get("settings_fingerprint") != settings_fingerprint(
        browsers=browsers, cookie_domains=cookie_domains
    ):
        return None
    if not str(data.get("cookie_header") or "").strip():
        return None

    expires_at = _parse_iso(str(data.get("expires_at") or ""))
    if expires_at is None or datetime.now(timezone.utc) >= expires_at:
        return None

    return data


def save_session(
    *,
    browsers: tuple[str, ...],
    cookie_domains: tuple[str, ...],
    browser: str,
    cookie_header: str,
    cookie_count: int,
) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=cache_ttl_seconds())
    payload = {
        "cookie_header": cookie_header,
        "browser": browser,
        "cookie_domains": list(cookie_domains),
        "cookie_count": cookie_count,
        "settings_fingerprint": settings_fingerprint(
            browsers=browsers, cookie_domains=cookie_domains
        ),
        "updated_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def clear_session() -> None:
    path = session_path()
    if path.is_file():
        path.unlink()


def session_status(
    *,
    browsers: tuple[str, ...],
    cookie_domains: tuple[str, ...],
) -> dict[str, Any]:
    path = session_path()
    data = load_session(browsers=browsers, cookie_domains=cookie_domains)
    status: dict[str, Any] = {
        "cache_enabled": cache_enabled(),
        "cache_path": str(path),
        "cached": data is not None,
        "ttl_seconds": cache_ttl_seconds(),
    }
    if data:
        status["updated_at"] = data.get("updated_at")
        status["expires_at"] = data.get("expires_at")
        status["browser"] = data.get("browser")
    return status


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
