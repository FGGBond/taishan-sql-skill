from __future__ import annotations

import json
from typing import Any


def success(data: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data if data is not None else {}, "warnings": []}
    payload.update(extra)
    return payload


def failure(error_code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "message": message,
        "recoverable": error_code in {"AUTH_EXPIRED", "AUTH_UNAVAILABLE", "HTTP_ERROR"},
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


def normalize_api_response(spec: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    response_spec = spec.get("response", {})
    ok_path = response_spec.get("ok_path")
    ok_value = response_spec.get("ok_value")
    actual_ok = get_path(raw, ok_path)

    if actual_ok != ok_value:
        error_message = get_path(raw, response_spec.get("error_path"), "Taishan API 返回失败")
        return failure("API_ERROR", str(error_message), raw=raw)

    data = get_path(raw, response_spec.get("data_path"), raw)
    if response_spec.get("data_encoding") == "json_string":
        data = parse_json_string(data)

    normalized: dict[str, Any] = {"raw": raw, "result": data}

    execute_time_path = response_spec.get("execute_time_path")
    if execute_time_path:
        normalized["execute_time_ms"] = get_path(raw, execute_time_path)

    if spec.get("name") == "query_data":
        normalized["rows"] = flatten_query_rows(data)
        normalized.pop("result", None)

    return success(normalized)


def flatten_query_rows(data_list: Any) -> list[dict[str, Any]]:
    if isinstance(data_list, dict):
        rows: list[dict[str, Any]] = []
        for key in sorted(data_list.keys(), key=str):
            value = data_list[key]
            if isinstance(value, list):
                rows.extend(item for item in value if isinstance(item, dict))
        return rows
    if isinstance(data_list, list):
        return [item for item in data_list if isinstance(item, dict)]
    return []
