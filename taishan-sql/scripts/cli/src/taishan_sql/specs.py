from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from .config import Settings, load_settings


class SpecError(RuntimeError):
    """Raised when an interface spec cannot be loaded."""


@dataclass(frozen=True)
class ApiSpec:
    name: str
    raw: dict[str, Any]
    path: Path

    @property
    def method(self) -> str:
        return str(self.raw.get("method", "GET")).upper()

    @property
    def base_url(self) -> str:
        return str(self.raw["base_url"]).rstrip("/")

    @property
    def endpoint_path(self) -> str:
        return str(self.raw["path"])


_SPEC_FILES = {
    "list_root_sources": "list-root-sources.yaml",
    "list_children_sources": "list-children-sources.yaml",
    "query_data": "query-data.yaml",
    "get_user_info": "get-user-info.yaml",
}


def load_spec(name: str, settings: Settings | None = None) -> ApiSpec:
    settings = settings or load_settings()
    filename = _SPEC_FILES.get(name, f"{name}.yaml")
    path = settings.specs_dir / filename

    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - installation dependent
        raise SpecError("缺少 PyYAML 依赖，请先安装项目依赖") from exc

    raw_text = _read_spec_text(path, filename)
    raw = yaml.safe_load(raw_text)
    if not isinstance(raw, dict):
        raise SpecError(f"接口 spec 格式无效：{path}")
    if "name" not in raw or "base_url" not in raw or "path" not in raw:
        raise SpecError(f"接口 spec 缺少必要字段：{path}")

    return ApiSpec(name=str(raw["name"]), raw=raw, path=path)


def _read_spec_text(path: Path, filename: str) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")

    packaged = resources.files("taishan_sql").joinpath("spec_data", filename)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")

    raise SpecError(f"找不到接口 spec：{path}")
