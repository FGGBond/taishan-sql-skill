from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .client import TaishanClient
from .normalize import failure, success


@dataclass(frozen=True)
class DatabaseTarget:
    app_name: str
    domain: str
    db_name: str
    source: dict[str, Any]


def resolve_database(client: TaishanClient, keyword: str, environment: str = "prod") -> dict[str, Any]:
    request_context = {"environment": environment}
    roots = client.call("list_root_sources", request_context)
    if not roots.get("ok"):
        return roots

    candidates = _filter_nodes(roots["data"].get("result", []), keyword)
    if not candidates:
        return failure("NOT_FOUND", f"未找到匹配数据源：{keyword}")
    if len(candidates) > 1:
        return success(
            {
                "matches": candidates,
                "message": "匹配到多个数据源，请使用更精确的 keyword 或显式指定 app/domain/db",
            },
            warnings=["ambiguous_database"],
        )

    app_node = candidates[0]
    domain_result = client.call(
        "list_children_sources",
        {"id": app_node["id"], "environment": environment},
    )
    if not domain_result.get("ok"):
        return domain_result

    domains = domain_result["data"].get("result", [])
    if not domains:
        return failure("NOT_FOUND", f"数据源无 domain 子节点：{app_node.get('text')}")

    if len(domains) > 1:
        return success(
            {"matches": domains, "message": "匹配到多个 domain，请显式指定 app/domain/db"},
            warnings=["ambiguous_domain"],
        )

    domain_node = domains[0]
    database_result = client.call(
        "list_children_sources",
        {"id": domain_node["id"], "environment": environment},
    )
    if not database_result.get("ok"):
        return database_result

    databases = database_result["data"].get("result", [])
    if not databases:
        return failure("NOT_FOUND", f"domain 无 database 子节点：{domain_node.get('text')}")

    if len(databases) > 1:
        return success(
            {"matches": databases, "message": "匹配到多个 database，请显式指定 app/domain/db"},
            warnings=["ambiguous_database"],
        )

    db_node = databases[0]
    target = DatabaseTarget(
        app_name=str(db_node.get("appName") or app_node.get("text") or app_node.get("appName")),
        domain=str(db_node.get("domain") or domain_node.get("domain")),
        db_name=str(db_node.get("dbName") or app_node.get("dbName")),
        source=db_node,
    )
    return success(
        {
            "app_name": target.app_name,
            "domain": target.domain,
            "db_name": target.db_name,
            "source": target.source,
        }
    )


def _filter_nodes(nodes: Any, keyword: str) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        return []

    normalized_keyword = keyword.lower()
    matches: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("parent") == "#":
            continue
        haystack = " ".join(
            str(node.get(field, "")) for field in ("id", "text", "dbName", "domain", "appName")
        ).lower()
        if normalized_keyword in haystack:
            matches.append(node)
    return matches
