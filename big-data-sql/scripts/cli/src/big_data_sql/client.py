from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .auth import AuthError, auth_headers
from .config import RunProfile, Settings, load_settings
from .normalize import failure


class PlatformClient:
    """HTTP client for big-data script center APIs (internal only)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def add_script(self, git_project_id: str) -> dict[str, Any]:
        profile = self.settings.profile
        body = {
            "type": int(profile.script_type),
            "gitProjectId": git_project_id,
            "isShow": 1,
            "gitProjectDirPath": "",
            "content": "",
            "templateId": 0,
            "isTemplate": False,
            "pythonType": 0,
            "beeSource": profile.bee_source,
            "showLeftPart": True,
        }
        return self._request_json(
            "POST",
            f"{self.settings.dp_base_url}/scriptcenter/script/addScript.ajax",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        )

    def save_content(self, content: str, script_file_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"{self.settings.dp_base_url}/scriptcenter/script/saveContent.ajax",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            body=json.dumps({"content": content, "id": script_file_id}, ensure_ascii=False).encode(
                "utf-8"
            ),
        )

    def script_right_check(self, content: str, profile: RunProfile) -> dict[str, Any]:
        fields = self._run_form_fields(content, profile)
        body, content_type = _encode_multipart(fields)
        return self._request_json(
            "POST",
            f"{self.settings.dp_base_url}/scriptcenter/check/scriptRightCheck.ajax",
            headers={"Content-Type": content_type},
            body=body,
        )

    def run_sql(self, content: str, profile: RunProfile) -> dict[str, Any]:
        fields = self._run_form_fields(content, profile)
        return self._request_form(
            f"{self.settings.dp_base_url}/scriptcenter/script/run.ajax",
            fields,
        )

    def poll_runtime_log(
        self,
        run_detail_id: str,
        *,
        current_log_index: int,
        start_row_key: str,
        has_finish_request_times: int,
    ) -> dict[str, Any]:
        fields = {
            "runDetailId": run_detail_id,
            "currentLogIndex": str(current_log_index),
            "hasFinishRequestTimes": str(has_finish_request_times),
            "projectSpaceId": "0",
            "searchType": "hbase",
            "searchError": "false",
            "searchKey": "",
        }
        if start_row_key:
            fields["startRowKey"] = start_row_key
        return self._request_form(
            f"{self.settings.script_center_base_url}/scriptcenter/script/runTimeLogV2.ajax",
            fields,
        )

    def fetch_title(self, run_detail_id: str, pre_key: str) -> dict[str, Any]:
        return self._request_form(
            f"{self.settings.dp_base_url}/scriptcenter/script/title.ajax",
            {"runDetailId": run_detail_id, "preKey": pre_key},
        )

    def fetch_run_data(
        self,
        run_detail_id: str,
        pre_key: str,
        *,
        page: int,
        rows: int,
    ) -> dict[str, Any]:
        return self._request_form(
            f"{self.settings.dp_base_url}/scriptcenter/script/runData.ajax",
            {
                "runDetailId": run_detail_id,
                "rows": str(rows),
                "page": str(page),
                "preKey": pre_key,
            },
        )

    def _run_form_fields(self, content: str, profile: RunProfile) -> dict[str, str]:
        return {
            "gitProjectId": profile.git_project_id,
            "beeSource": profile.bee_source,
            "scriptFileId": profile.script_file_id,
            "content": content,
            "runType": profile.run_type,
            "dbName": profile.db_name,
            "doSqlToolCheck": "false",
            "runClusterCode": profile.cluster_code,
            "marketLinuxUser": profile.market_linux_user,
            "accountCode": profile.account_code,
            "queueCode": profile.queue_code,
            "engineType": profile.engine_type,
            "args": "[]",
            "businessLineFromQueue": profile.business_line,
            "scriptType": profile.script_type,
            "scriptId": profile.script_file_id,
            "clusterCode": profile.cluster_code,
            "marketCode": profile.market_code,
        }

    def _request_form(self, url: str, fields: dict[str, str]) -> dict[str, Any]:
        body = urlencode(fields).encode("utf-8")
        return self._request_json(
            "POST",
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=body,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            request_headers = self._common_headers()
            if headers:
                request_headers.update(headers)
            request = Request(url, data=body, headers=request_headers, method=method)
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except AuthError as exc:
            return failure("AUTH_UNAVAILABLE", str(exc))
        except HTTPError as exc:
            return failure("HTTP_ERROR", f"HTTP {exc.code}: {exc.reason}", status=exc.code)
        except URLError as exc:
            return failure("NETWORK_ERROR", str(exc.reason))
        except TimeoutError as exc:
            return failure("TIMEOUT", str(exc))

        elapsed_ms = round((time.monotonic() - started) * 1000)
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            return failure("INVALID_JSON", "接口返回不是有效 JSON", body=raw_body, elapsed_ms=elapsed_ms)

        if not _api_ok(parsed):
            message = str(parsed.get("message") or parsed.get("msg") or "平台接口返回失败")
            return failure("API_ERROR", message, elapsed_ms=elapsed_ms)

        parsed["_elapsed_ms"] = elapsed_ms
        return parsed

    def _common_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": self.settings.dp_base_url,
            "Referer": f"{self.settings.dp_base_url}/query/index.html",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }
        headers.update(auth_headers(self.settings))
        return headers


def _api_ok(payload: dict[str, Any]) -> bool:
    if payload.get("success") is True:
        return True
    if payload.get("code") in (0, "0", 200, "200"):
        return True
    if payload.get("status") == "success":
        return True
    return False


def _encode_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----BigDataSql{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}\r\n".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        lines.append(value.encode("utf-8"))
        lines.append(b"\r\n")
    lines.append(f"--{boundary}--\r\n".encode())
    content_type = f"multipart/form-data; boundary={boundary}"
    return b"".join(lines), content_type
