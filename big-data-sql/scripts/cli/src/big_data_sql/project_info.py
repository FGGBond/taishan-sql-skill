from __future__ import annotations

import os
from typing import Any

from .config import Settings, load_settings
from .normalize import failure


def extract_local_project(api_result: dict[str, Any]) -> dict[str, Any] | None:
    if api_result.get("error_code"):
        return None
    if api_result.get("success") is not True:
        return None
    obj = api_result.get("obj")
    if not isinstance(obj, dict):
        return None

    git_project_id = str(obj.get("gitProjectId") or obj.get("id") or "").strip()
    if not git_project_id:
        return None

    return {
        "git_project_id": git_project_id,
        "git_project_name": str(obj.get("gitProjectName") or obj.get("gitProjectPath") or ""),
        "has_authority": bool(obj.get("hasAuthority")),
        "description": str(obj.get("description") or ""),
    }


def resolve_git_project_for_init(
    settings: Settings | None = None,
    *,
    use_saved_profile: bool = True,
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve git project id for init: env > profile.json > getErpLocalProject API."""
    settings = settings or load_settings()

    env_id = os.getenv("BDP_SQL_GIT_PROJECT_ID", "").strip()
    if env_id:
        return env_id, None

    if use_saved_profile:
        from .profile_store import load_saved_profile

        saved = load_saved_profile() or {}
        saved_id = str(saved.get("git_project_id") or "").strip()
        if saved_id:
            return saved_id, None

    from .client import PlatformClient

    resp = PlatformClient(settings).get_erp_local_project(track=False)
    project = extract_local_project(resp)
    if not project:
        message = str(resp.get("message") or "无法获取当前 ERP 的本地代码库")
        return None, failure(
            "GIT_PROJECT_UNAVAILABLE",
            message,
            next_action="doctor",
            raw=resp if isinstance(resp, dict) else None,
        )

    return project["git_project_id"], None
