from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .auth import AuthError, load_browser_cookies
from .client import TaishanClient
from .config import load_settings
from .normalize import failure, success
from .resolver import resolve_database
from .sql_guard import is_dql
from .tracking import track_cli_command
from .user_info import get_user_erp


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "handler"):
        parser.print_help()
        return

    environment = getattr(args, "env", "prod")
    track_cli_command(args.command, environment=environment)
    result = args.handler(args)
    print_json(result)
    if not result.get("ok", False):
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taishan-sql",
        description="AI-callable CLI for Taishan database query platform",
    )
    subparsers = parser.add_subparsers(dest="command")

    doctor = subparsers.add_parser("doctor", help="检查本地配置与浏览器认证状态")
    doctor.set_defaults(handler=handle_doctor)

    sources = subparsers.add_parser("sources", help="列出当前账号有权限的数据源根节点")
    add_env_argument(sources)
    sources.set_defaults(handler=handle_sources)

    children = subparsers.add_parser("children", help="根据节点 ID 查询下一级数据源节点")
    children.add_argument("--id", required=True, help="Taishan 数据源树节点 ID")
    add_env_argument(children)
    children.set_defaults(handler=handle_children)

    resolve = subparsers.add_parser("resolve-db", help="根据关键字解析 appName/domain/dbName")
    resolve.add_argument("--keyword", required=True, help="库名、应用名、节点文本或域名关键字")
    add_env_argument(resolve)
    resolve.set_defaults(handler=handle_resolve_db)

    query = subparsers.add_parser("query", help="执行 Taishan SQL 查询")
    query_target = query.add_mutually_exclusive_group(required=True)
    query_target.add_argument("--keyword", help="自动解析数据库目标的关键字")
    query_target.add_argument("--app-name", help="Taishan queryData body.appName")
    query.add_argument("--domain", help="Taishan queryData body.domain")
    query.add_argument("--db-name", help="Taishan queryData body.dbName")
    query.add_argument("--sql", required=True, help="需要执行的 SQL")
    add_env_argument(query)
    query.add_argument("--desensitize", type=int, default=1, help="是否启用平台脱敏，默认 1")
    query.set_defaults(handler=handle_query)

    return parser


def add_env_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", choices=("prod", "test"), default="prod", help="执行环境，默认 prod")


def handle_doctor(_: argparse.Namespace) -> dict[str, Any]:
    settings = load_settings()
    try:
        cookie_result = load_browser_cookies(settings)
    except AuthError as exc:
        return failure(
            "AUTH_UNAVAILABLE",
            str(exc),
            settings={
                "browsers": settings.browsers,
                "cookie_domains": settings.cookie_domains,
                "specs_dir": str(settings.specs_dir),
            },
        )

    return success(
        {
            "auth": "ok",
            "browser": cookie_result.browser,
            "cookie_count": cookie_result.cookie_count,
            "cookie_domains": cookie_result.domains,
            "specs_dir": str(settings.specs_dir),
            "erp": get_user_erp(settings),
        }
    )


def handle_sources(args: argparse.Namespace) -> dict[str, Any]:
    return TaishanClient().call("list_root_sources", {"environment": args.env})


def handle_children(args: argparse.Namespace) -> dict[str, Any]:
    return TaishanClient().call("list_children_sources", {"id": args.id, "environment": args.env})


def handle_resolve_db(args: argparse.Namespace) -> dict[str, Any]:
    return resolve_database(TaishanClient(), args.keyword, args.env)


def handle_query(args: argparse.Namespace) -> dict[str, Any]:
    dql_ok, dql_message = is_dql(args.sql)
    if not dql_ok:
        return failure("NOT_DQL", dql_message, recoverable=False)

    client = TaishanClient()
    if args.keyword:
        resolved = resolve_database(client, args.keyword, args.env)
        if not resolved.get("ok"):
            return resolved
        target = resolved.get("data", {})
        missing = [key for key in ("app_name", "domain", "db_name") if key not in target]
        if missing:
            return failure("AMBIGUOUS_TARGET", "无法唯一解析数据库目标", resolution=target)
        app_name = target["app_name"]
        domain = target["domain"]
        db_name = target["db_name"]
    else:
        if not args.domain or not args.db_name:
            return failure(
                "INVALID_ARGUMENT",
                "显式指定 --app-name 时必须同时提供 --domain 和 --db-name",
                recoverable=False,
            )
        app_name = args.app_name
        domain = args.domain
        db_name = args.db_name

    return client.call(
        "query_data",
        {
            "app_name": app_name,
            "domain": domain,
            "db_name": db_name,
            "sql": args.sql,
            "environment": args.env,
            "desensitize": args.desensitize,
        },
    )


def print_json(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
