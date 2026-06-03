from __future__ import annotations

from typing import Any

from .client import PlatformClient
from .config import Settings, load_settings
from .normalize import failure, success
from .profile_store import profile_path, profile_status, save_profile
from .project_info import extract_local_project, resolve_git_project_for_init


def run_init(*, force: bool = False, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    status = profile_status()

    if status["initialized"] and not force:
        return success(
            status="initialized",
            message="已有有效 profile，跳过创建。使用 init --force 可新建脚本文件。",
            data={
                "script_file_id": status["script_file_id"],
                "git_project_id": status["git_project_id"],
                "script_name": status.get("script_name"),
            },
            files={"profile": status["profile_path"]},
            next_action="run",
        )

    git_project_id, resolve_error = resolve_git_project_for_init(
        settings, use_saved_profile=not force
    )
    if resolve_error:
        return resolve_error
    if not git_project_id:
        return failure(
            "GIT_PROJECT_UNAVAILABLE",
            "未获取到 git project id。请登录 dp.jd.com 后重试，或设置 BDP_SQL_GIT_PROJECT_ID。",
            next_action="doctor",
        )

    client = PlatformClient(settings)
    resp = client.add_script(git_project_id)
    if not resp.get("ok", True) and "error_code" in resp:
        return failure(
            str(resp.get("error_code") or "INIT_FAILED"),
            str(resp.get("message") or "创建脚本失败"),
            git_project_id=git_project_id,
            next_action="doctor",
        )

    obj = resp.get("obj") or {}
    script_file_id = str(obj.get("id") or "")
    if not script_file_id:
        return failure(
            "INIT_FAILED",
            "addScript 成功但未返回脚本 id",
            next_action="doctor",
        )

    resolved_git = str(obj.get("gitProjectId") or git_project_id)
    script_name = str(obj.get("name") or "")
    saved_path = save_profile(
        script_file_id=script_file_id,
        git_project_id=resolved_git,
        script_name=script_name,
        source="addScript",
    )

    refreshed = load_settings()

    return success(
        status="initialized",
        message="已通过 addScript 创建 CLI 专用脚本并保存 profile",
        data={
            "script_file_id": script_file_id,
            "git_project_id": resolved_git,
            "script_name": script_name,
            "version": obj.get("version"),
        },
        files={"profile": str(saved_path)},
        settings={
            "profile_path": str(profile_path()),
            "script_file_id": refreshed.profile.script_file_id,
            "git_project_id": refreshed.profile.git_project_id,
        },
        next_action="run",
    )


def require_profile(settings: Settings | None = None) -> dict[str, Any] | None:
    """若未 init 且未通过环境变量提供 script_file_id，返回失败信封。"""
    settings = settings or load_settings()
    if settings.profile.script_file_id:
        return None
    status = profile_status()
    return failure(
        "PROFILE_NOT_INITIALIZED",
        "未找到 scriptFileId。请先执行：big-data-sql init",
        files={"profile": status["profile_path"]},
        next_action="init",
        recoverable=True,
    )
