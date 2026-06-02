from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import RunProfile, Settings


class ArtifactSession:
    """Per-run artifact directory and persisted state."""

    def __init__(self, root: Path, run_detail_id: str | None = None) -> None:
        self.run_detail_id = run_detail_id or "pending"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        short = uuid.uuid4().hex[:8]
        self.dir = root / f"{self.run_detail_id}_{stamp}_{short}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "result").mkdir(exist_ok=True)

    @classmethod
    def open_existing(cls, artifact_dir: Path) -> ArtifactSession:
        session = cls.__new__(cls)
        session.dir = artifact_dir.resolve()
        if not session.dir.is_dir():
            raise FileNotFoundError(f"artifact 目录不存在：{session.dir}")
        meta = session.read_json("meta.json", default={})
        session.run_detail_id = str(meta.get("run_detail_id", session.dir.name.split("_")[0]))
        return session

    def rename_for_run(self, run_detail_id: str) -> None:
        """Submit 成功后，将目录名中的 pending/draft 替换为真实 run_detail_id。"""
        self.run_detail_id = run_detail_id
        if self.dir.name.startswith(("pending_", "draft_")):
            new_name = self.dir.name.replace(self.dir.name.split("_")[0], run_detail_id, 1)
            new_dir = self.dir.parent / new_name
            if not new_dir.exists():
                self.dir.rename(new_dir)
                self.dir = new_dir

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def write_sql(self, sql: str) -> Path:
        target = self.path("sql.sql")
        target.write_text(sql, encoding="utf-8")
        return target

    def write_meta(self, meta: dict[str, Any]) -> Path:
        return self.write_json("meta.json", meta)

    def write_state(self, state: dict[str, Any]) -> Path:
        return self.write_json("state.json", state)

    def read_state(self) -> dict[str, Any]:
        return self.read_json("state.json", default={})

    def append_logs(self, lines: list[str]) -> Path:
        target = self.path("logs.txt")
        with target.open("a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line.rstrip("\n") + "\n")
        return target

    def write_error(self, error: dict[str, Any]) -> Path:
        return self.write_json("error.json", error)

    def write_envelope(self, envelope: dict[str, Any]) -> Path:
        return self.write_json("envelope.json", envelope)

    def write_json(self, name: str, data: Any) -> Path:
        target = self.path(name)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def read_json(self, name: str, default: Any = None) -> Any:
        target = self.path(name)
        if not target.exists():
            return default
        return json.loads(target.read_text(encoding="utf-8"))

    def file_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {
            "sql": str(self.path("sql.sql")),
            "state": str(self.path("state.json")),
            "logs": str(self.path("logs.txt")),
        }
        if self.path("error.json").exists():
            mapping["error"] = str(self.path("error.json"))
        result_json = self.path("result", "data.json")
        result_csv = self.path("result", "data.csv")
        columns_json = self.path("result", "columns.json")
        if columns_json.exists():
            mapping["columns_json"] = str(columns_json)
        if result_json.exists():
            mapping["result_json"] = str(result_json)
        if result_csv.exists():
            mapping["result_csv"] = str(result_csv)
        mapping["envelope"] = str(self.path("envelope.json"))
        return mapping

    def log_tail(self, max_lines: int = 20) -> str:
        logs_path = self.path("logs.txt")
        if not logs_path.exists():
            return ""
        lines = logs_path.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-max_lines:])

    @staticmethod
    def build_meta(
        sql: str,
        run_detail_id: str,
        profile: RunProfile,
        settings: Settings,
    ) -> dict[str, Any]:
        return {
            "run_detail_id": run_detail_id,
            "sql": sql,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "profile": asdict(profile),
            "engine_type": profile.engine_type,
            "cluster_code": profile.cluster_code,
            "db_name": profile.db_name,
        }

    @staticmethod
    def initial_state(run_detail_id: str, pre_key: str) -> dict[str, Any]:
        return {
            "run_detail_id": run_detail_id,
            "current_log_index": 0,
            "start_row_key": "",
            "has_finish_request_times": 0,
            "can_open_result": False,
            "result_fetched": False,
            "is_last_log": False,
            "is_error_log": False,
            "pre_key": pre_key,
            "started_at": time.time(),
        }
