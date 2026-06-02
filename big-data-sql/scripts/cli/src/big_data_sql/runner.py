from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from .artifacts import ArtifactSession
from .client import PlatformClient
from .config import Settings, load_settings
from .init_cmd import require_profile
from .normalize import failure, success


class SqlRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.client = PlatformClient(self.settings)

    def run(
        self,
        sql: str,
        *,
        output_dir: Path | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        sql = sql.strip()
        if not sql:
            return failure("INVALID_ARGUMENT", "SQL 不能为空", recoverable=False)

        profile_error = require_profile(self.settings)
        if profile_error:
            return profile_error

        root = output_dir or self.settings.output_dir
        root.mkdir(parents=True, exist_ok=True)
        session = ArtifactSession(root)
        session.write_sql(sql)

        profile = self.settings.profile

        save_resp = self.client.save_content(sql, profile.script_file_id)
        if not save_resp.get("ok", True) and "error_code" in save_resp:
            return self._finalize_failure(session, save_resp, sql, step="save_content")

        check_resp = self.client.script_right_check(sql, profile)
        if not check_resp.get("ok", True) and "error_code" in check_resp:
            return self._finalize_failure(session, check_resp, sql, step="script_right_check")

        run_resp = self.client.run_sql(sql, profile)
        if not run_resp.get("ok", True) and "error_code" in run_resp:
            return self._finalize_failure(session, run_resp, sql, step="run")

        run_detail_id = str(run_resp.get("obj", {}).get("id", ""))
        if not run_detail_id:
            return self._finalize_failure(
                session,
                failure("API_ERROR", "提交运行成功但未返回 runDetailId"),
                sql,
                step="run",
            )

        session.run_detail_id = run_detail_id
        session.rename_for_run(run_detail_id)
        session.write_meta(
            ArtifactSession.build_meta(sql, run_detail_id, profile, self.settings)
        )
        state = ArtifactSession.initial_state(run_detail_id, profile.pre_key)
        session.write_state(state)

        if not wait:
            envelope = self._running_envelope(session, state, message="任务已提交，请使用 poll 继续查询")
            session.write_envelope(envelope)
            return envelope

        return self._wait_until_done(session, state)

    def poll(self, artifact_dir: Path) -> dict[str, Any]:
        try:
            session = ArtifactSession.open_existing(artifact_dir)
        except FileNotFoundError as exc:
            return failure("NOT_FOUND", str(exc), recoverable=False)

        state = session.read_state()
        if not state:
            return failure("INVALID_STATE", "缺少 state.json，无法续轮询", artifact_dir=str(session.dir))

        if state.get("is_last_log") and state.get("result_fetched"):
            return self._build_final_envelope(session, state)

        return self._poll_once(session, state, finalize=True)

    def _wait_until_done(self, session: ArtifactSession, state: dict[str, Any]) -> dict[str, Any]:
        deadline = time.monotonic() + self.settings.wait_timeout_seconds
        last_envelope: dict[str, Any] | None = None

        while time.monotonic() < deadline:
            envelope = self._poll_once(session, state, finalize=False)
            last_envelope = envelope
            status = envelope.get("status")
            if status in {"success", "failed"}:
                session.write_envelope(envelope)
                return envelope
            time.sleep(self.settings.poll_interval_seconds)

        running = self._running_envelope(
            session,
            state,
            message=(
                f"等待超时（{self.settings.wait_timeout_seconds}s），任务仍在运行。"
                f"请使用 poll --artifact-dir {session.dir} 继续查询"
            ),
        )
        session.write_envelope(running)
        return running

    def _poll_once(
        self,
        session: ArtifactSession,
        state: dict[str, Any],
        *,
        finalize: bool,
    ) -> dict[str, Any]:
        run_detail_id = str(state["run_detail_id"])
        poll_resp = self.client.poll_runtime_log(
            run_detail_id,
            current_log_index=int(state.get("current_log_index", 0)),
            start_row_key=str(state.get("start_row_key") or ""),
            has_finish_request_times=int(state.get("has_finish_request_times", 0)),
        )
        if not poll_resp.get("ok", True) and "error_code" in poll_resp:
            return self._finalize_failure(session, poll_resp, step="poll")

        obj = poll_resp.get("obj") or {}
        logs = obj.get("logs") or []
        if logs:
            session.append_logs([str(item.get("content", "")) for item in logs])

        state["current_log_index"] = int(obj.get("currentLogIndex", state.get("current_log_index", 0)))
        state["start_row_key"] = str(obj.get("startRowKey") or state.get("start_row_key") or "")
        state["can_open_result"] = bool(obj.get("canOpenResult"))
        state["is_last_log"] = bool(obj.get("isLastLog"))
        state["is_error_log"] = bool(obj.get("isErrorLog"))
        if state["is_last_log"]:
            state["has_finish_request_times"] = int(state.get("has_finish_request_times", 0)) + 1

        run_detail = obj.get("runDetail") or {}
        state["response_code"] = str(run_detail.get("responseCode", ""))

        if state["can_open_result"] and not state.get("result_fetched"):
            fetch_error = self._fetch_and_save_results(session, state)
            if fetch_error:
                return fetch_error

        session.write_state(state)

        if finalize or state.get("is_last_log"):
            return self._build_final_envelope(session, state)

        return self._running_envelope(session, state)

    def _fetch_and_save_results(
        self,
        session: ArtifactSession,
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        run_detail_id = str(state["run_detail_id"])
        pre_key = str(state.get("pre_key") or self.settings.profile.pre_key)

        title_resp = self.client.fetch_title(run_detail_id, pre_key)
        if not title_resp.get("ok", True) and "error_code" in title_resp:
            return self._finalize_failure(session, title_resp, step="fetch_title")

        columns_map = title_resp.get("obj") or {}
        column_names = _ordered_column_names(columns_map, pre_key)
        session.write_json("result/columns.json", columns_map)

        page = 1
        page_size = self.settings.result_page_size
        all_rows: list[dict[str, Any]] = []
        total_rows: int | None = None

        while True:
            data_resp = self.client.fetch_run_data(
                run_detail_id,
                pre_key,
                page=page,
                rows=page_size,
            )
            if not data_resp.get("ok", True) and "error_code" in data_resp:
                return self._finalize_failure(session, data_resp, step="fetch_run_data")

            rows = data_resp.get("data") or []
            all_rows.extend(rows)
            if total_rows is None:
                total_rows = _parse_int(data_resp.get("totals"))
            if not rows:
                break
            if total_rows is not None and len(all_rows) >= total_rows:
                break
            if len(rows) < page_size:
                break
            page += 1

        normalized_rows = [_normalize_row(row, column_names, pre_key) for row in all_rows]
        result_payload = {
            "columns": column_names,
            "rows": normalized_rows,
            "row_count": len(normalized_rows),
            "column_count": len(column_names),
        }
        session.write_json("result/data.json", result_payload)
        _write_csv(session.path("result", "data.csv"), column_names, normalized_rows)
        state["result_fetched"] = True
        state["row_count"] = len(normalized_rows)
        state["column_count"] = len(column_names)
        return None

    def _build_final_envelope(self, session: ArtifactSession, state: dict[str, Any]) -> dict[str, Any]:
        failed = bool(state.get("is_error_log")) or _is_failed_response(state.get("response_code"))
        log_tail = session.log_tail()

        if failed:
            error_payload = {
                "response_code": state.get("response_code"),
                "is_error_log": state.get("is_error_log"),
                "log_tail": log_tail,
            }
            session.write_error(error_payload)
            envelope = failure(
                "SQL_EXEC_FAILED",
                "SQL 执行失败，详细日志已保存",
                command="poll" if state.get("has_finish_request_times") else "run",
                status="failed",
                run_id=state.get("run_detail_id"),
                artifact_dir=str(session.dir),
                files=session.file_map(),
                log_tail=_truncate_text(log_tail, self.settings.preview_max_chars),
                next_action="read_logs",
            )
            session.write_envelope(envelope)
            return envelope

        meta = session.read_json("meta.json", default={})
        summary = {
            "row_count": state.get("row_count", 0),
            "column_count": state.get("column_count", 0),
            "engine": meta.get("engine_type") or self.settings.profile.engine_type,
            "cluster": meta.get("cluster_code") or self.settings.profile.cluster_code,
            "exit_code": 0,
            "elapsed_ms": round((time.time() - float(state.get("started_at", time.time()))) * 1000),
        }
        preview = self._build_preview(session)
        message = "查询成功"
        if preview.get("truncated"):
            message = (
                f"查询成功。完整结果共 {preview.get('total_chars', 0)} 字符，"
                f"stdout 仅展示 {preview.get('shown_chars', 0)} 字符。"
                f"请读取 files.result_json 或 files.result_csv。"
            )

        envelope = success(
            command="poll" if state.get("has_finish_request_times") else "run",
            status="success",
            run_id=state.get("run_detail_id"),
            artifact_dir=str(session.dir),
            files=session.file_map(),
            summary=summary,
            preview=preview,
            next_action="read_result",
            message=message,
        )
        session.write_envelope(envelope)
        return envelope

    def _running_envelope(
        self,
        session: ArtifactSession,
        state: dict[str, Any],
        *,
        message: str | None = None,
    ) -> dict[str, Any]:
        log_tail = session.log_tail()
        return success(
            command="run",
            status="running",
            run_id=state.get("run_detail_id"),
            artifact_dir=str(session.dir),
            files=session.file_map(),
            log_tail=_truncate_text(log_tail, self.settings.preview_max_chars),
            next_action="poll",
            message=message or "任务运行中，请继续 poll",
        )

    def _build_preview(self, session: ArtifactSession) -> dict[str, Any]:
        result_path = session.path("result", "data.json")
        if not result_path.exists():
            return {"columns": [], "rows": [], "truncated": False, "shown_chars": 0, "total_chars": 0}

        payload = json.loads(result_path.read_text(encoding="utf-8"))
        columns = payload.get("columns") or []
        rows = payload.get("rows") or []
        preview_rows = rows[: self.settings.preview_max_rows]

        full_text = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False)
        preview_text = json.dumps({"columns": columns, "rows": preview_rows}, ensure_ascii=False)
        max_chars = self.settings.preview_max_chars
        if len(preview_text) > max_chars:
            preview_text = preview_text[:max_chars]

        truncated = len(full_text) > len(preview_text) or len(rows) > len(preview_rows)
        return {
            "columns": columns,
            "rows": preview_rows,
            "truncated": truncated,
            "shown_chars": len(preview_text),
            "total_chars": len(full_text),
        }

    def _finalize_failure(
        self,
        session: ArtifactSession,
        error: dict[str, Any],
        sql: str | None = None,
        *,
        step: str,
    ) -> dict[str, Any]:
        if sql:
            session.write_sql(sql)
        error_payload = {
            "step": step,
            "error_code": error.get("error_code"),
            "message": error.get("message"),
        }
        session.write_error(error_payload)
        envelope = failure(
            str(error.get("error_code") or "EXEC_FAILED"),
            str(error.get("message") or "执行失败"),
            command="run",
            status="failed",
            run_id=session.run_detail_id,
            artifact_dir=str(session.dir),
            files=session.file_map(),
            log_tail=session.log_tail(),
            next_action="read_logs",
        )
        session.write_envelope(envelope)
        return envelope


def _ordered_column_names(columns_map: dict[str, Any], pre_key: str) -> list[str]:
    if not columns_map:
        return []
    indexed: list[tuple[int, str]] = []
    for key, label in columns_map.items():
        if not str(key).startswith(pre_key):
            continue
        suffix = str(key)[len(pre_key) :]
        try:
            indexed.append((int(suffix), str(label)))
        except ValueError:
            indexed.append((999999, str(label)))
    indexed.sort(key=lambda item: item[0])
    return [label for _, label in indexed]


def _normalize_row(row: dict[str, Any], column_names: list[str], pre_key: str) -> dict[str, Any]:
    if not column_names:
        return dict(row)
    keys = sorted(
        [key for key in row if str(key).startswith(pre_key)],
        key=lambda key: int(str(key)[len(pre_key) :]) if str(key)[len(pre_key) :].isdigit() else 999999,
    )
    normalized: dict[str, Any] = {}
    for index, column in enumerate(column_names):
        source_key = keys[index] if index < len(keys) else column
        normalized[column] = row.get(source_key, row.get(column, ""))
    return normalized


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns or ["value"], extrasaction="ignore")
        if columns:
            writer.writeheader()
        for row in rows:
            writer.writerow(row if columns else {"value": json.dumps(row, ensure_ascii=False)})


def _parse_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_failed_response(response_code: Any) -> bool:
    if response_code is None or response_code == "":
        return False
    return str(response_code) not in {"0", "200"}


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...（已截断，完整日志见 logs.txt，共 {len(text)} 字符）"
