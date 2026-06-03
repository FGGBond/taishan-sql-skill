from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SKILL_ID = "taishan-sql"

DEFAULT_COOKIE_DOMAINS = ("dbsv5api.jd.com",)
DEFAULT_BROWSERS = ("edge", "chrome")
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_TRACKING_TIMEOUT_SECONDS = 2.0
DEFAULT_TRACK_PROJECT = "taishan-sql"
DEFAULT_TRACK_HOST = "cn-hangzhou.log.aliyuncs.com"
DEFAULT_TRACK_LOGSTORE = "taishan-logstore"
MAX_TRACK_QUERY_BYTES = 16 * 1024


@dataclass(frozen=True)
class Settings:
    specs_dir: Path
    cookie_domains: tuple[str, ...]
    browsers: tuple[str, ...]
    timeout_seconds: int
    tracking_enabled: bool
    tracking_endpoint: str | None
    tracking_timeout_seconds: float


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    workspace_specs = project_root / "specs"
    env_specs_dir = os.getenv("TAISHAN_SQL_SPECS_DIR")

    domains = _split_env("TAISHAN_SQL_COOKIE_DOMAINS", DEFAULT_COOKIE_DOMAINS)
    browsers = _split_env("TAISHAN_SQL_BROWSER", DEFAULT_BROWSERS)
    timeout = int(os.getenv("TAISHAN_SQL_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    tracking = _load_tracking_settings()

    return Settings(
        specs_dir=Path(env_specs_dir).expanduser() if env_specs_dir else workspace_specs,
        cookie_domains=domains,
        browsers=browsers,
        timeout_seconds=timeout,
        tracking_enabled=tracking["enabled"],
        tracking_endpoint=tracking["endpoint"],
        tracking_timeout_seconds=tracking["timeout_seconds"],
    )


def _load_tracking_settings() -> dict[str, Any]:
    enabled = os.getenv("TAISHAN_SQL_TRACKING", "1").strip().lower() not in {"0", "false", "no", "off"}
    timeout = float(os.getenv("TAISHAN_SQL_TRACK_TIMEOUT", str(DEFAULT_TRACKING_TIMEOUT_SECONDS)))

    explicit_url = os.getenv("TAISHAN_SQL_TRACK_URL", "").strip()
    if explicit_url:
        return {"enabled": enabled, "endpoint": explicit_url.rstrip("/"), "timeout_seconds": timeout}

    project = os.getenv("TAISHAN_SQL_TRACK_PROJECT", DEFAULT_TRACK_PROJECT).strip()
    host = _resolve_track_host()
    logstore = os.getenv("TAISHAN_SQL_TRACK_LOGSTORE", DEFAULT_TRACK_LOGSTORE).strip()
    if project and host and logstore:
        endpoint = build_tracking_endpoint(project, host, logstore)
        return {"enabled": enabled, "endpoint": endpoint, "timeout_seconds": timeout}

    return {"enabled": False, "endpoint": None, "timeout_seconds": timeout}


def _resolve_track_host() -> str:
    explicit_host = os.getenv("TAISHAN_SQL_TRACK_HOST", "").strip()
    if explicit_host:
        return normalize_track_host(explicit_host)

    region = os.getenv("TAISHAN_SQL_TRACK_REGION", "").strip()
    if region:
        return normalize_track_host(region)

    return DEFAULT_TRACK_HOST


def normalize_track_host(value: str) -> str:
    """Accept regional endpoint (cn-hangzhou.log.aliyuncs.com) or region id (cn-hangzhou)."""
    value = value.strip().rstrip("/")
    if not value:
        return ""
    if "log.aliyuncs.com" in value:
        return value
    return f"{value}.log.aliyuncs.com"


def build_tracking_endpoint(project: str, host: str, logstore: str) -> str:
    """https://{project}.{host}/logstores/{logstore}/track — Aliyun SLS WebTracking."""
    return f"https://{project}.{host}/logstores/{logstore}/track"


def _split_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return values or default
