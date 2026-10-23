"""Small validated user settings surface; credentials stay with Nexa."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime.run_state import RunConfig

BUDGET_KEYS = {"max_model_calls", "max_tool_calls", "timeout"}


def read(workspace: Path) -> dict[str, Any]:
    path = workspace / ".nexa-code" / "settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    validate(settings)
    return settings


def validate(settings: dict[str, Any]) -> None:
    if not isinstance(settings, dict) or settings.keys() - BUDGET_KEYS - {"theme", "editorMode"}:
        raise ValueError("Supported settings: theme, editorMode, max_model_calls, max_tool_calls, timeout")
    if settings.get("theme", "graphite") not in {"graphite", "light"}:
        raise ValueError("theme must be graphite or light")
    if settings.get("editorMode", "normal") not in {"normal", "vim"}:
        raise ValueError("editorMode must be normal or vim")
    RunConfig(**{key: value for key, value in settings.items() if key in BUDGET_KEYS})


def write(workspace: Path, settings: dict[str, Any]) -> None:
    validate(settings)
    path = workspace / ".nexa-code" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    temporary.replace(path)
