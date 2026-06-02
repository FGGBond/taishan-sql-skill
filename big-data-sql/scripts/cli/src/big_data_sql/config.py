from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

SUPPORTED_ENGINE_TYPES: tuple[str, ...] = ("presto", "spark", "doris")
DEFAULT_ENGINE_TYPE = "presto"


DEFAULT_COOKIE_DOMAINS = ("dp.jd.com", "scriptcenter.dp.jd.com", "jd.com")
DEFAULT_BROWSERS = ("edge", "chrome")
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_WAIT_TIMEOUT_SECONDS = 120
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_OUTPUT_DIR = Path.home() / ".cache" / "big-data-sql" / "runs"
DEFAULT_PREVIEW_MAX_CHARS = 4096
DEFAULT_PREVIEW_MAX_ROWS = 20
DEFAULT_RESULT_PAGE_SIZE = 100

DEFAULT_DP_BASE = "http://dp.jd.com"
DEFAULT_SCRIPT_CENTER_BASE = "http://scriptcenter.dp.jd.com"
DEFAULT_GIT_PROJECT_ID = "1000669346"


@dataclass(frozen=True)
class RunProfile:
    script_file_id: str
    git_project_id: str
    engine_type: str
    db_name: str
    cluster_code: str
    market_code: str
    market_linux_user: str
    account_code: str
    queue_code: str
    business_line: str
    pre_key: str
    bee_source: str
    script_type: str
    run_type: str


@dataclass(frozen=True)
class Settings:
    dp_base_url: str
    script_center_base_url: str
    cookie_domains: tuple[str, ...]
    browsers: tuple[str, ...]
    timeout_seconds: int
    wait_timeout_seconds: int
    poll_interval_seconds: float
    output_dir: Path
    preview_max_chars: int
    preview_max_rows: int
    result_page_size: int
    profile: RunProfile


def load_settings() -> Settings:
    from .profile_store import resolve_script_ids

    script_file_id, git_project_id = resolve_script_ids(
        env_script_file_id=os.getenv("BDP_SQL_SCRIPT_FILE_ID"),
        env_git_project_id=os.getenv("BDP_SQL_GIT_PROJECT_ID"),
        default_git_project_id=DEFAULT_GIT_PROJECT_ID,
    )
    profile = RunProfile(
        script_file_id=script_file_id,
        git_project_id=git_project_id,
        engine_type=_engine_from_env(),
        db_name=os.getenv("BDP_SQL_DB_NAME", "dw_api"),
        cluster_code=os.getenv("BDP_SQL_CLUSTER_CODE", "cairne"),
        market_code=os.getenv("BDP_SQL_MARKET_CODE", "mart_tc"),
        market_linux_user=os.getenv("BDP_SQL_MARKET_LINUX_USER", "mart_tc"),
        account_code=os.getenv("BDP_SQL_ACCOUNT_CODE", "mart_tc_jddj_ks_product"),
        queue_code=os.getenv(
            "BDP_SQL_QUEUE_CODE",
            "root.mart_tc.mart_tc_jddj.mart_tc_jddj_query",
        ),
        business_line=os.getenv("BDP_SQL_BUSINESS_LINE", "mart_tc_jddj"),
        pre_key=os.getenv("BDP_SQL_PRE_KEY", "cccc_"),
        bee_source=os.getenv("BDP_SQL_BEE_SOURCE", "ide_online"),
        script_type=os.getenv("BDP_SQL_SCRIPT_TYPE", "1"),
        run_type=os.getenv("BDP_SQL_RUN_TYPE", "0"),
    )

    output_raw = os.getenv("BDP_SQL_OUTPUT_DIR")
    output_dir = Path(output_raw).expanduser() if output_raw else DEFAULT_OUTPUT_DIR

    return Settings(
        dp_base_url=os.getenv("BDP_SQL_DP_BASE_URL", DEFAULT_DP_BASE).rstrip("/"),
        script_center_base_url=os.getenv(
            "BDP_SQL_SCRIPT_CENTER_BASE_URL", DEFAULT_SCRIPT_CENTER_BASE
        ).rstrip("/"),
        cookie_domains=_split_env("BDP_SQL_COOKIE_DOMAINS", DEFAULT_COOKIE_DOMAINS),
        browsers=_split_env("BDP_SQL_BROWSER", DEFAULT_BROWSERS),
        timeout_seconds=int(os.getenv("BDP_SQL_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))),
        wait_timeout_seconds=int(
            os.getenv("BDP_SQL_WAIT_TIMEOUT", str(DEFAULT_WAIT_TIMEOUT_SECONDS))
        ),
        poll_interval_seconds=float(
            os.getenv("BDP_SQL_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL_SECONDS))
        ),
        output_dir=output_dir,
        preview_max_chars=int(
            os.getenv("BDP_SQL_PREVIEW_MAX_CHARS", str(DEFAULT_PREVIEW_MAX_CHARS))
        ),
        preview_max_rows=int(
            os.getenv("BDP_SQL_PREVIEW_MAX_ROWS", str(DEFAULT_PREVIEW_MAX_ROWS))
        ),
        result_page_size=int(
            os.getenv("BDP_SQL_RESULT_PAGE_SIZE", str(DEFAULT_RESULT_PAGE_SIZE))
        ),
        profile=profile,
    )


def normalize_engine_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_ENGINE_TYPES:
        allowed = ", ".join(SUPPORTED_ENGINE_TYPES)
        raise ValueError(f"不支持的 engineType: {value!r}，可选: {allowed}")
    return normalized


def _engine_from_env() -> str:
    return normalize_engine_type(os.getenv("BDP_SQL_ENGINE_TYPE", DEFAULT_ENGINE_TYPE))


def with_engine(settings: Settings, engine: str | None) -> Settings:
    """按次运行覆盖 engineType（CLI --engine）。"""
    if engine is None:
        return settings
    engine_type = normalize_engine_type(engine)
    return replace(settings, profile=replace(settings.profile, engine_type=engine_type))


def _split_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    return values or default
