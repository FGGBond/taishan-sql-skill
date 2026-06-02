from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from .auth import AuthError, load_browser_cookies
from .client import ApiClient
from .config import load_settings
from .normalize import failure, success

Handler = Callable[[argparse.Namespace], dict[str, Any]]


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return

    try:
        result = args.handler(args)
    except Exception as exc:  # last-resort guard so Agent always gets JSON
        result = failure(getattr(args, "command", "unknown"), "INTERNAL_ERROR", str(exc), recoverable=False)

    print_json(result)
    if not result.get("ok", False):
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="{{CLI_NAME}}",
        description="{{CLI_DESCRIPTION}}",
    )
    parser.add_argument("--verbose", action="store_true", help="Include elapsed_ms in output")
    parser.add_argument("--include-raw", action="store_true", help="Include upstream JSON at data._raw")
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="检查本地配置与浏览器认证状态")
    doctor.set_defaults(handler=handle_doctor)

    {{SUBCOMMAND_REGISTRATIONS}}

    return parser


def add_env_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=("prod", "test"), default="prod", help="执行环境，默认 prod")


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    add_env_argument(parser)


def handle_doctor(args: argparse.Namespace) -> dict[str, Any]:
    settings = load_settings()
    try:
        cookie_result = load_browser_cookies(settings)
    except AuthError as exc:
        return failure(
            "doctor",
            "AUTH_UNAVAILABLE",
            str(exc),
            settings={
                "browsers": settings.browsers,
                "cookie_domains": settings.cookie_domains,
                "specs_dir": str(settings.specs_dir),
            },
        )

    return success(
        "doctor",
        {
            "auth": "ok",
            "browser": cookie_result.browser,
            "cookie_count": cookie_result.cookie_count,
            "cookie_domains": cookie_result.domains,
            "specs_dir": str(settings.specs_dir),
        },
    )


{{SUBCOMMAND_HANDLERS}}


def print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
