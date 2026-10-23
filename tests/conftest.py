from __future__ import annotations

import os
from pathlib import Path

import pytest

collect_ignore_glob = ["legacy/*.py"]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEXA_QUIET", "1")
    monkeypatch.delenv("NEXA_PERMISSION_MODE", raising=False)
    return tmp_path


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("NEXA_CODE_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="Set NEXA_CODE_INTEGRATION=1 for explicit network/provider/desktop integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
