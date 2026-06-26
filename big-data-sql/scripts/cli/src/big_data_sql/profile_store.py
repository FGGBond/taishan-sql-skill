from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_DIR = Path.home() / ".config" / "big-data-sql"
DEFAULT_PROFILE_FILE = DEFAULT_PROFILE_DIR / "profile.json"


def profile_path() -> Path:
    raw = os.getenv("BDP_SQL_PROFILE_PATH")
    return Path(raw).expanduser() if raw else DEFAULT_PROFILE_FILE


def load_saved_profile() -> dict[str, Any] | None:
    path = profile_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def save_profile(
    *,
    script_file_id: str,
    git_project_id: str,
    script_name: str = "",
    source: str = "addScript",
    run_config: dict[str, str] | None = None,
) -> Path:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_saved_profile() or {}
    payload: dict[str, Any] = {
        "script_file_id": script_file_id,
        "git_project_id": git_project_id,
        "script_name": script_name,
        "created_at": existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    if run_config:
        for key in (
            "market_linux_user",
            "market_code",
            "market_name",
            "account_code",
            "account_name",
            "queue_code",
            "queue_name",
            "business_line",
            "cluster_code",
            "target_index",
        ):
            value = str(run_config.get(key) or "").strip()
            if value:
                payload[key] = value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def merge_run_config(run_config: dict[str, str]) -> Path | None:
    """Update market/account/queue fields on an existing profile."""
    existing = load_saved_profile()
    if not existing or not existing.get("script_file_id"):
        return None
    return save_profile(
        script_file_id=str(existing["script_file_id"]),
        git_project_id=str(existing.get("git_project_id") or ""),
        script_name=str(existing.get("script_name") or ""),
        source=str(existing.get("source") or "targetSelect"),
        run_config=run_config,
    )


def resolve_script_ids(
    *,
    env_script_file_id: str | None,
    env_git_project_id: str | None,
) -> tuple[str, str]:
    """环境变量 > profile.json（无个人默认 git project）。"""
    saved = load_saved_profile() or {}
    git_project_id = env_git_project_id or str(saved.get("git_project_id") or "")
    script_file_id = env_script_file_id or str(saved.get("script_file_id") or "")
    return script_file_id, git_project_id


def profile_status() -> dict[str, Any]:
    saved = load_saved_profile()
    path = profile_path()
    if not saved:
        return {
            "initialized": False,
            "profile_path": str(path),
            "script_file_id": "",
            "git_project_id": "",
        }
    return {
        "initialized": bool(saved.get("script_file_id")),
        "profile_path": str(path),
        "script_file_id": str(saved.get("script_file_id") or ""),
        "git_project_id": str(saved.get("git_project_id") or ""),
        "script_name": str(saved.get("script_name") or ""),
        "created_at": saved.get("created_at"),
        "source": saved.get("source"),
        "market_linux_user": str(saved.get("market_linux_user") or ""),
        "account_code": str(saved.get("account_code") or ""),
        "queue_code": str(saved.get("queue_code") or ""),
        "target_index": saved.get("target_index"),
        "market_name": str(saved.get("market_name") or ""),
        "account_name": str(saved.get("account_name") or ""),
        "queue_name": str(saved.get("queue_name") or ""),
    }
