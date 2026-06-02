from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .auth import AuthError, load_browser_cookies
from .config import SUPPORTED_ENGINE_TYPES, load_settings, with_engine
from .init_cmd import run_init
from .normalize import failure, success
from .profile_store import profile_status
from .runner import SqlRunner


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return

    result = args.handler(args)
    print_json(result)
    if not result.get("ok", False) and result.get("status") != "running":
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="big-data-sql",
        description="AI-callable CLI for JD big-data platform SQL execution",
    )
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="检查浏览器认证与运行配置")
    doctor.set_defaults(handler=handle_doctor)

    init = subparsers.add_parser("init", help="创建 CLI 专用脚本并保存 scriptFileId")
    init.add_argument(
        "--force",
        action="store_true",
        help="即使已有 profile 也重新 addScript 并覆盖",
    )
    init.set_defaults(handler=handle_init)

    run = subparsers.add_parser("run", help="提交并执行 SQL")
    run.add_argument("--sql", required=True, help="需要执行的 SQL")
    run.add_argument(
        "--output-dir",
        help="artifact 保存目录，默认 ~/.cache/big-data-sql/runs 或 BDP_SQL_OUTPUT_DIR",
    )
    run.add_argument(
        "--no-wait",
        action="store_true",
        help="提交后立即返回，后续使用 poll 查询状态",
    )
    run.add_argument(
        "--engine",
        choices=SUPPORTED_ENGINE_TYPES,
        help="执行引擎 engineType：presto（默认）、spark、doris",
    )
    run.set_defaults(handler=handle_run)

    poll = subparsers.add_parser("poll", help="续轮询运行中的任务并拉取结果")
    poll.add_argument(
        "--artifact-dir",
        required=True,
        help="run 命令返回的 artifact_dir 路径",
    )
    poll.set_defaults(handler=handle_poll)

    return parser


def handle_doctor(_: argparse.Namespace) -> dict[str, Any]:
    settings = load_settings()
    try:
        cookie_result = load_browser_cookies(settings)
    except AuthError as exc:
        return failure(
            "AUTH_UNAVAILABLE",
            str(exc),
            settings=_public_settings(settings),
        )

    prof = profile_status()
    return success(
        status="ready",
        message="认证与配置检查通过",
        auth={
            "browser": cookie_result.browser,
            "cookie_count": cookie_result.cookie_count,
            "cookie_domains": cookie_result.domains,
        },
        profile=prof,
        settings=_public_settings(settings),
        next_action="init" if not prof.get("initialized") else "run",
    )


def handle_init(args: argparse.Namespace) -> dict[str, Any]:
    return run_init(force=args.force)


def handle_run(args: argparse.Namespace) -> dict[str, Any]:
    try:
        settings = with_engine(load_settings(), args.engine)
    except ValueError as exc:
        return failure(
            "INVALID_ARGUMENT",
            str(exc),
            recoverable=False,
            supported_engines=list(SUPPORTED_ENGINE_TYPES),
        )
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else None
    return SqlRunner(settings).run(
        args.sql,
        output_dir=output_dir,
        wait=not args.no_wait,
    )


def handle_poll(args: argparse.Namespace) -> dict[str, Any]:
    settings = load_settings()
    return SqlRunner(settings).poll(Path(args.artifact_dir).expanduser())


def _public_settings(settings: Any) -> dict[str, Any]:
    profile = settings.profile
    prof = profile_status()
    return {
        "output_dir": str(settings.output_dir),
        "wait_timeout_seconds": settings.wait_timeout_seconds,
        "engine_type": profile.engine_type,
        "supported_engines": list(SUPPORTED_ENGINE_TYPES),
        "db_name": profile.db_name,
        "cluster_code": profile.cluster_code,
        "account_code": profile.account_code,
        "queue_code": profile.queue_code,
        "script_file_id": profile.script_file_id,
        "git_project_id": profile.git_project_id,
        "profile_path": prof.get("profile_path"),
        "profile_initialized": prof.get("initialized"),
    }


def print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
