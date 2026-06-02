from __future__ import annotations

import re
from typing import Final

_DQL_START_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH"}
)

_FORBIDDEN_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "TRUNCATE",
        "ALTER",
        "CREATE",
        "REPLACE",
        "MERGE",
        "GRANT",
        "REVOKE",
        "CALL",
        "EXEC",
        "EXECUTE",
        "RENAME",
        "LOAD",
        "OUTFILE",
        "INFILE",
        "HANDLER",
        "LOCK",
        "UNLOCK",
        "KILL",
        "SET",
        "USE",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "VACUUM",
        "ANALYZE",
        "OPTIMIZE",
        "REPAIR",
        "BACKUP",
        "RESTORE",
        "SHUTDOWN",
    }
)

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def is_dql(sql: str) -> tuple[bool, str]:
    """Return whether SQL is read-only DQL (no DML/DDL)."""
    statements = _split_statements(sql)
    if not statements:
        return False, "SQL 不能为空"

    for statement in statements:
        ok, message = _is_dql_statement(statement)
        if not ok:
            return False, message
    return True, ""


def _split_statements(sql: str) -> list[str]:
    cleaned = _strip_strings(_strip_comments(sql))
    parts = [part.strip() for part in cleaned.split(";")]
    return [part for part in parts if part]


def _is_dql_statement(statement: str) -> tuple[bool, str]:
    tokens = _scan_words(statement)
    if not tokens:
        return False, "SQL 不能为空"

    first = tokens[0].upper()
    if first not in _DQL_START_KEYWORDS:
        allowed = ", ".join(sorted(_DQL_START_KEYWORDS))
        return False, f"仅允许 DQL（查询类 SQL），首关键字为 {first!r}，允许：{allowed}"

    forbidden = [word for word in tokens if word.upper() in _FORBIDDEN_KEYWORDS]
    if forbidden:
        return False, f"检测到非 DQL 关键字：{', '.join(sorted({w.upper() for w in forbidden}))}"

    return True, ""


def _scan_words(statement: str) -> list[str]:
    return _WORD_RE.findall(statement)


def _strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return without_line


def _strip_strings(sql: str) -> str:
    return re.sub(r"""('([^'\\]|\\.)*'|"([^"\\]|\\.)*")""", " ", sql)
