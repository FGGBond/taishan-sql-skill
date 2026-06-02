from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_COOKIE_DOMAINS = ("dbsv5api.jd.com",)
DEFAULT_BROWSERS = ("edge", "chrome")
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Settings:
    specs_dir: Path
    cookie_domains: tuple[str, ...]
    browsers: tuple[str, ...]
    timeout_seconds: int


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[2]
    workspace_specs = project_root / "specs"
    env_specs_dir = os.getenv("TAISHAN_SQL_SPECS_DIR")

    domains = _split_env("TAISHAN_SQL_COOKIE_DOMAINS", DEFAULT_COOKIE_DOMAINS)
    browsers = _split_env("TAISHAN_SQL_BROWSER", DEFAULT_BROWSERS)
    timeout = int(os.getenv("TAISHAN_SQL_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))

    return Settings(
        specs_dir=Path(env_specs_dir).expanduser() if env_specs_dir else workspace_specs,
        cookie_domains=domains,
        browsers=browsers,
        timeout_seconds=timeout,
    )


def _split_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return values or default
