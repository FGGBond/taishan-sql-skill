from __future__ import annotations

import getpass
import os
import platform
import uuid
from pathlib import Path


def get_device_id() -> str:
    """Return a stable per-machine device id for usage tracking."""
    path = _device_id_path()
    if path.is_file():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    device_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"taishan-sql:{_machine_fingerprint()}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(device_id + "\n", encoding="utf-8")
    return device_id


def _device_id_path() -> Path:
    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        base = Path(config_home).expanduser()
    else:
        base = Path.home() / ".config"
    return base / "taishan-sql" / "device_id"


def _machine_fingerprint() -> str:
    parts: list[str] = [getpass.getuser()]

    try:
        parts.append(platform.node() or "")
    except Exception:  # pragma: no cover - platform dependent
        pass

    parts.append(platform.system())
    parts.append(platform.machine())

    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            if path.is_file():
                parts.append(path.read_text(encoding="utf-8").strip())
                break
        except OSError:
            continue

    return "|".join(part for part in parts if part)
