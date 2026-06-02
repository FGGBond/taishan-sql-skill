from __future__ import annotations

import json
from typing import Any

CLI_NAME = "{{CLI_NAME}}"

ERROR_GUIDANCE: dict[str, dict[str, Any]] = {
    "AUTH_UNAVAILABLE": {
        "recoverable": True,
        "next_step": f"Run `{CLI_NAME} doctor`. If still failing, ask the user to log in to the platform in Edge or Chrome, then retry.",
    },
    "AUTH_EXPIRED": {
        "recoverable": True,
        "next_step": f"Run `{CLI_NAME} doctor`. Ask the user to refresh their browser session, then retry.",
    },
    "INVALID_ARGUMENT": {
        "recoverable": False,
        "next_step": f"Fix CLI flags using `{CLI_NAME} <command> --help` and retry.",
    },
    "HTTP_ERROR": {
        "recoverable": True,
        "next_step": "Retry once. If it persists, check `--env` and platform availability.",
    },
    "NETWORK_ERROR": {
        "recoverable": True,
        "next_step": "Retry once. If it persists, report a network connectivity issue.",
    },
    "TIMEOUT": {
        "recoverable": True,
        "next_step": "Retry with a smaller request, add LIMIT, or split the task.",
    },
    "INVALID_JSON": {
        "recoverable": False,
        "next_step": "Report that the platform returned non-JSON; do not guess payload fields.",
    },
    "API_ERROR": {
        "recoverable": False,
        "next_step": "Read `message`, explain to the user, and adjust inputs if the error is actionable.",
    },
    "AMBIGUOUS_TARGET": {
        "recoverable": True,
        "next_step": "Present `candidates` to the user, pick one, and retry with explicit parameters.",
    },
    "INTERNAL_ERROR": {
        "recoverable": False,
        "next_step": "Report an unexpected CLI failure. Do not retry blindly; inspect stderr if available.",
    },
}


def success(tool: str, data: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "tool": tool, "data": data if data is not None else {}}
    payload.update(extra)
    return payload


def failure(
    tool: str,
    error_code: str,
    message: str,
    *,
    recoverable: bool | None = None,
    next_step: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    guidance = ERROR_GUIDANCE.get(error_code, {})
    payload: dict[str, Any] = {
        "ok": False,
        "tool": tool,
        "error_code": error_code,
        "message": message,
        "recoverable": recoverable if recoverable is not None else guidance.get("recoverable", False),
        "next_step": next_step or guidance.get("next_step", "Read `message` and stop unless a clear retry is possible."),
    }
    payload.update(extra)
    return payload


def get_path(payload: Any, dotted_path: str | None, default: Any = None) -> Any:
    if not dotted_path:
        return default

    current = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _rename_keys(value: Any, rename: dict[str, str]) -> Any:
    if not rename:
        return value
    if isinstance(value, dict):
        return {rename.get(key, key): item for key, item in value.items()}
    if isinstance(value, list):
        return [_rename_keys(item, rename) for item in value]
    return value


def _pick_fields(value: Any, fields: list[str] | None) -> Any:
    if not fields or not isinstance(value, dict):
        return value
    return {field: value[field] for field in fields if field in value}


def _trim_list(items: Any, fields: list[str] | None, rename: dict[str, str]) -> list[Any]:
    if not isinstance(items, list):
        return []
    trimmed: list[Any] = []
    for item in items:
        picked = _pick_fields(item, fields)
        trimmed.append(_rename_keys(picked, rename))
    return trimmed


def shape_agent_data(spec: dict[str, Any], extracted: Any, *, include_raw: bool = False, raw: Any = None) -> dict[str, Any]:
    agent_spec = spec.get("response", {}).get("agent_output", {})
    output_type = agent_spec.get("type", "object")
    fields = agent_spec.get("item_fields")
    rename = agent_spec.get("rename", {})

    if output_type == "list":
        data: dict[str, Any] = {"items": _trim_list(extracted, fields, rename)}
    elif output_type == "rows":
        rows = _trim_list(extracted, fields, rename)
        data = {"rows": rows, "row_count": len(rows)}
    else:
        if isinstance(extracted, dict):
            picked = _pick_fields(extracted, fields) if fields else extracted
            data = _rename_keys(picked, rename)
            if not isinstance(data, dict):
                data = {"value": data}
        else:
            data = {"value": extracted}

    if include_raw and raw is not None:
        data["_raw"] = raw
    return data


def normalize_api_response(
    spec: dict[str, Any],
    raw: dict[str, Any],
    *,
    tool: str,
    include_raw: bool = False,
) -> dict[str, Any]:
    response_spec = spec.get("response", {})
    ok_path = response_spec.get("ok_path")
    ok_value = response_spec.get("ok_value")
    actual_ok = get_path(raw, ok_path)

    if actual_ok != ok_value:
        error_message = get_path(raw, response_spec.get("error_path"), "API 返回失败")
        return failure(tool, "API_ERROR", str(error_message))

    extracted = get_path(raw, response_spec.get("data_path"), raw)
    if response_spec.get("data_encoding") == "json_string":
        extracted = parse_json_string(extracted)

    execute_time_path = response_spec.get("execute_time_path")
    data = shape_agent_data(spec, extracted, include_raw=include_raw, raw=raw if include_raw else None)
    if execute_time_path:
        execute_time = get_path(raw, execute_time_path)
        if execute_time is not None:
            data["execute_time_ms"] = execute_time

    return success(tool, data)
