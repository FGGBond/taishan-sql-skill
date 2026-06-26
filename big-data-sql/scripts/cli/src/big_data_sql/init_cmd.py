from __future__ import annotations

from typing import Any

from .account_config import resolve_run_config_for_init
from .client import PlatformClient
from .config import Settings, load_settings
from .normalize import failure, success
from .profile_store import merge_run_config, profile_path, profile_status, save_profile
from .project_info import resolve_git_project_for_init


def run_init(
    *,
    force: bool = False,
    target_index: int | None = None,
    account_code: str | None = None,
    queue_code: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings()
    status = profile_status()

    if status["initialized"] and not force:
        needs_market = not (status.get("account_code") and status.get("queue_code"))
        if needs_market or target_index or account_code:
            run_config, run_error = resolve_run_config_for_init(
                settings,
                use_saved_profile=not (target_index or account_code),
                target_index=target_index,
                account_code=account_code,
                queue_code=queue_code,
            )
            if run_error:
                return run_error
            save_profile(
                script_file_id=status["script_file_id"],
                git_project_id=status["git_project_id"],
                script_name=str(status.get("script_name") or ""),
                source="targetSelect",
                run_config=run_config,
            )
            return _init_success_existing(status, run_config, "已更新 profile 中的集市/账号/队列配置")
        return success(
            status="initialized",
            message="已有有效 profile，跳过创建。使用 init --force 可新建脚本文件。",
            data={
                "script_file_id": status["script_file_id"],
                "git_project_id": status["git_project_id"],
                "script_name": status.get("script_name"),
                "account_code": status.get("account_code"),
                "queue_code": status.get("queue_code"),
            },
            files={"profile": status["profile_path"]},
            next_action="run",
        )

    run_config, run_error = resolve_run_config_for_init(
        settings,
        use_saved_profile=False,
        target_index=target_index,
        account_code=account_code,
        queue_code=queue_code,
    )
    if run_error:
        return run_error

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
        run_config=run_config,
    )

    refreshed = load_settings()

    return success(
        status="initialized",
        message="已通过 addScript 创建 CLI 专用脚本并保存 profile（含集市/队列配置）",
        data={
            "script_file_id": script_file_id,
            "git_project_id": resolved_git,
            "script_name": script_name,
            "version": obj.get("version"),
            "market_linux_user": run_config.get("market_linux_user") if run_config else "",
            "account_code": run_config.get("account_code") if run_config else "",
            "queue_code": run_config.get("queue_code") if run_config else "",
            "target_label": _target_label(run_config),
        },
        files={"profile": str(saved_path)},
        settings={
            "profile_path": str(profile_path()),
            "script_file_id": refreshed.profile.script_file_id,
            "git_project_id": refreshed.profile.git_project_id,
        },
        next_action="run",
    )


def _init_success_existing(
    status: dict[str, Any], run_config: dict[str, str] | None, message: str
) -> dict[str, Any]:
    return success(
        status="initialized",
        message=message,
        data={
            "script_file_id": status["script_file_id"],
            "git_project_id": status["git_project_id"],
            "market_linux_user": run_config.get("market_linux_user") if run_config else "",
            "account_code": run_config.get("account_code") if run_config else "",
            "queue_code": run_config.get("queue_code") if run_config else "",
            "target_label": _target_label(run_config),
        },
        files={"profile": status["profile_path"]},
        next_action="run",
    )


def _target_label(run_config: dict[str, str] | None) -> str:
    if not run_config:
        return ""
    return (
        f"{run_config.get('market_name', '')} / {run_config.get('account_name', '')} / "
        f"{run_config.get('queue_name', '')}"
    ).strip(" /")


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


def ensure_run_target(
    settings: Settings,
    *,
    target_index: int | None = None,
    account_code: str | None = None,
    queue_code: str | None = None,
) -> tuple[Settings | None, dict[str, Any] | None]:
    from .account_config import resolve_run_config
    from .config import with_run_config

    run_config, error = resolve_run_config(
        settings,
        target_index=target_index,
        account_code=account_code,
        queue_code=queue_code,
    )
    if error:
        return None, error
    if not run_config:
        return None, failure("TARGET_UNAVAILABLE", "未能解析执行目标", next_action="list-targets")
    merge_run_config(run_config)
    return with_run_config(settings, run_config), None
