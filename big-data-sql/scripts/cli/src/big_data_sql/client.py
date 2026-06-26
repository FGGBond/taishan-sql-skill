from __future__ import annotations

import json
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .auth import AuthError, auth_headers, invalidate_auth_cache, load_browser_cookies
from .config import RunProfile, Settings, load_settings
from .http_util import ssl_context
from .normalize import failure
from .tracking import track_api_call


class PlatformClient:
    """HTTP client for big-data script center APIs (internal only)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def get_login_user(self, *, track: bool = True) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.settings.dp_base_url}/request/portal/common/loginUser",
            track_action="get_login_user" if track else None,
        )

    def get_erp_local_project(self, *, track: bool = True) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.settings.dp_base_url}/scriptcenter/project/getErpLocalProject.ajax",
            track_action="get_erp_local_project" if track else None,
        )

    def get_markets_by_erp(self, *, track: bool = True) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.settings.dp_base_url}/scriptcenter/config/getMarketByErp.ajax",
            track_action="get_markets_by_erp" if track else None,
        )

    def get_accounts_by_erp(self, linux_user: str | None = None, *, track: bool = True) -> dict[str, Any]:
        query: dict[str, str] = {}
        if linux_user:
            query["linuxUser"] = linux_user
        return self._request_json(
            "GET",
            f"{self.settings.dp_base_url}/scriptcenter/config/getAccountByErp4DQ.ajax",
            query=query,
            track_action="get_accounts_by_erp" if track else None,
        )

    def get_queues_by_erp(
        self,
        linux_user: str,
        production_account_code: str,
        *,
        track: bool = True,
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.settings.dp_base_url}/scriptcenter/config/getQueueByErp.ajax",
            query={
                "linuxUser": linux_user,
                "productionAccountCode": production_account_code,
            },
            track_action="get_queues_by_erp" if track else None,
        )

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
            track_action="add_script",
        )

    def save_content(self, content: str, script_file_id: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"{self.settings.dp_base_url}/scriptcenter/script/saveContent.ajax",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            body=json.dumps({"content": content, "id": script_file_id}, ensure_ascii=False).encode(
                "utf-8"
            ),
            track_action="save_content",
        )

    def script_right_check(self, content: str, profile: RunProfile) -> dict[str, Any]:
        fields = self._run_form_fields(content, profile)
        body, content_type = _encode_multipart(fields)
        return self._request_json(
            "POST",
            f"{self.settings.dp_base_url}/scriptcenter/check/scriptRightCheck.ajax",
            headers={"Content-Type": content_type},
            body=body,
            track_action="script_right_check",
        )

    def run_sql(self, content: str, profile: RunProfile) -> dict[str, Any]:
        fields = self._run_form_fields(content, profile)
        return self._request_form(
            f"{self.settings.dp_base_url}/scriptcenter/script/run.ajax",
            fields,
            track_action="run_sql",
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
            track_action="poll_runtime_log",
        )

    def fetch_title(self, run_detail_id: str, pre_key: str) -> dict[str, Any]:
        return self._request_form(
            f"{self.settings.dp_base_url}/scriptcenter/script/title.ajax",
            {"runDetailId": run_detail_id, "preKey": pre_key},
            track_action="fetch_title",
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
            track_action="fetch_run_data",
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

    def _request_form(
        self,
        url: str,
        fields: dict[str, str],
        *,
        track_action: str | None = None,
    ) -> dict[str, Any]:
        body = urlencode(fields).encode("utf-8")
        return self._request_json(
            "POST",
            url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=body,
            track_action=track_action,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        track_action: str | None = None,
        _auth_retry: bool = True,
    ) -> dict[str, Any]:
        result = self._request_json_once(
            method,
            url,
            query=query,
            headers=headers,
            body=body,
            track_action=track_action,
        )
        if not _auth_retry or not _should_retry_auth(result, track_action=track_action):
            return result

        invalidate_auth_cache(self.settings)
        try:
            load_browser_cookies(self.settings, force_refresh=True)
        except AuthError:
            return result

        return self._request_json_once(
            method,
            url,
            query=query,
            headers=headers,
            body=body,
            track_action=track_action,
        )

    def _request_json_once(
        self,
        method: str,
        url: str,
        *,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        track_action: str | None = None,
    ) -> dict[str, Any]:
        if track_action and track_action != "get_login_user":
            track_api_call(track_action, self.settings)
        if query:
            encoded = urlencode({k: v for k, v in query.items() if v})
            if encoded:
                url = f"{url}?{encoded}"
        started = time.monotonic()
        try:
            request_headers = self._common_headers()
            if headers:
                request_headers.update(headers)
            request = Request(url, data=body, headers=request_headers, method=method)
            with urlopen(
                request, timeout=self.settings.timeout_seconds, context=ssl_context()
            ) as response:
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


def _should_retry_auth(result: dict[str, Any], *, track_action: str | None) -> bool:
    if track_action in {None, "get_login_user"}:
        return False
    return result.get("error_code") == "HTTP_ERROR" and result.get("status") == 401


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
