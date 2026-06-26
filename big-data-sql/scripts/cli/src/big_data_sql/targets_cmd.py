from __future__ import annotations

from typing import Any

from .account_config import _choices_for_display, list_run_targets
from .config import Settings, load_settings
from .normalize import success


def run_list_targets(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or load_settings()
    targets, error = list_run_targets(settings)
    if error:
        return error

    return success(
        status="targets",
        message=f"共 {len(targets)} 个可用的大数据执行目标",
        count=len(targets),
        choices=_choices_for_display(targets),
        next_action="run" if len(targets) == 1 else "select-target",
        hint=(
            "仅一个目标时可直接 run；多个时请 init/run --target-index <n> 或 --account-code <code>"
            if len(targets) > 1
            else None
        ),
    )
