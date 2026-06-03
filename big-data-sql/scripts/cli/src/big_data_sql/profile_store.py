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
) -> Path:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "script_file_id": script_file_id,
        "git_project_id": git_project_id,
        "script_name": script_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
    }
