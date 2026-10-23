from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from src.runtime.run_state import RunStatus
from test_session import call, reply

from nexa_code.commands import COMMAND_NAMES, run_command
from nexa_code.fixture_provider import FixtureProvider
from nexa_code.loader import APP_ROOT
from nexa_code.protocol import Emitter
from nexa_code.session import Session
from nexa_code.tool_services import active


def test_every_public_tool_and_command_remains_exposed(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    public = {
        name
        for path in (APP_ROOT / "src" / "tools").glob("*.nx")
        for name in re.findall(r"^fn (\w+)\(", path.read_text(), re.MULTILINE)
        if not name.startswith("_")
    }
    assert {tool["name"] for tool in session.agent.tools} == public
    assert len(public) == 50
    names = set(json.loads((APP_ROOT / "tests" / "fixtures" / "legacy-commands.json").read_text()))
    assert names == set(COMMAND_NAMES)
    for schema in session.agent.tools:
        assert callable(schema["_handler"])
        assert schema["requires_approval"]
    with active(session):
        discovered = session.namespace["SearchExtraTools"]("", "50")
    assert len(discovered.splitlines()) == 51
    assert "get_env_info" not in discovered


def test_read_edit_staleness_multiedit_and_notebook_regressions(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    tool = session.namespace
    path = workspace / "code.txt"
    path.write_text("alpha\nbeta\n")
    assert "Read" in tool["Edit"](str(path), "alpha", "ALPHA", False)
    tool["Read"](str(path), 0, 0, "")
    bad = json.dumps([{"old_string": "alpha", "new_string": "ALPHA"}, {"old_string": "missing", "new_string": "x"}])
    tool["MultiEdit"](str(path), bad)
    assert path.read_text() == "alpha\nbeta\n"
    tool["Edit"](str(path), "alpha", "ALPHA", False)
    assert path.read_text() == "ALPHA\nbeta\n"
    tool["Read"](str(path), 0, 0, "")
    path.write_text("changed outside\n")
    assert "modified" in tool["Edit"](str(path), "changed", "no", False).lower()
    nb = workspace / "note.ipynb"
    nb.write_text(
        json.dumps(
            {"cells": [{"cell_type": "code", "source": ["print(1)"], "outputs": [], "metadata": {}}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
        )
    )
    tool["Read"](str(nb), 0, 0, "")
    tool["NotebookEdit"](str(nb), "0", "print(42)", "code", "replace")
    assert "42" in nb.read_text()


def test_snapshots_survive_restart_and_undo_restores_original(workspace: Path) -> None:
    path = workspace / "code.txt"
    path.write_text("before")
    session = Session(workspace, provider=FixtureProvider([call("Write", {"file_path": "code.txt", "content": "after"}), reply("done")]))
    session.namespace["Read"](str(path), 0, 0, "")
    state = session.message("write")
    session.approve(state.run_id, "call-1", "allow_once")
    assert path.read_text() == "after"
    restored = Session(workspace, session_id=session.id, provider=FixtureProvider([]))
    assert "Restored" in run_command(restored, "/undo")
    assert path.read_text() == "before"


def test_unknown_actual_tool_outcome_requires_reconciliation(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([call("Write", {"file_path": "result", "content": "one"}), reply("reconciled")]))

    def ambiguous(file_path: str, content: str) -> str:
        (workspace / file_path).write_text(content)
        raise TimeoutError("Connection lost after external effect")

    for tool in session.agent.tools:
        if tool["name"] == "Write":
            tool["_handler"] = ambiguous
    state = session.message("write")
    state = session.approve(state.run_id, "call-1", "allow_once")
    assert state.status == RunStatus.FAILED
    assert state.tool_journal["call-1"]["status"] == "started"
    with pytest.raises(ValueError, match="unknown"):
        session.message("try again")
    result = session.resolve(state.run_id, "call-1", "Verified result file contains one", True)
    assert result.success
    assert (workspace / "result").read_text() == "one"


def test_remote_trigger_lost_response_stays_unknown(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    effects: list[bool] = []

    async def lost_response(*args: Any, **kwargs: Any) -> Any:
        effects.append(True)
        raise httpx.ReadTimeout("fixture lost response after POST")

    session = Session(workspace, provider=FixtureProvider([call("RemoteTrigger", {"url": "https://offline.invalid/fixture", "payload_json": "{}"})]))
    state = session.message("trigger")
    monkeypatch.setattr(httpx.AsyncClient, "send", lost_response)
    state = session.approve(state.run_id, "call-1", "allow_once")
    assert effects == [True]
    assert state.status == RunStatus.FAILED
    assert state.tool_journal["call-1"]["status"] == "started"
    with pytest.raises(ValueError, match="unknown"):
        session.message("continue")


@pytest.mark.parametrize(
    "name,arguments", [("ExecuteExtraTool", {"tool_name": "Read", "params_json": "{"}), ("MultiEdit", {"file_path": "sample.txt", "edits": "{"})]
)
def test_malformed_inner_parameters_remain_recoverable(workspace: Path, name: str, arguments: dict[str, object]) -> None:
    events: list[dict[str, Any]] = []
    session = Session(workspace, provider=FixtureProvider([call(name, arguments), reply("recovered"), reply("next")]), emitter=Emitter(callback=events.append))
    state = session.message("malformed parameters")
    if state.status == RunStatus.WAITING_APPROVAL:
        assert any(event["type"] == "permission_request" for event in events)
        state = session.approve(state.run_id, "call-1", "deny")
    assert state.success
    assert not state.tool_journal["call-1"]["success"]
    assert session.message("continue").success


def test_shell_cancellation_reaps_process(workspace: Path) -> None:
    session = Session(
        workspace, provider=FixtureProvider([call("Bash", {"command": "sleep 20", "timeout": 30000, "run_in_background": False}), reply("should not finish")])
    )
    state = session.message("long check")
    result: list[Any] = []
    worker = threading.Thread(target=lambda: result.append(session.approve(state.run_id, "call-1", "allow_once")))
    worker.start()
    deadline = time.monotonic() + 3
    while not session.processes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert session.processes
    processes = list(session.processes.values())
    session.cancel.set()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert result[0].status == RunStatus.CANCELLED
    assert all(process.poll() is not None for process in processes)


def test_tasks_todos_plan_and_artifacts(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    tool = session.namespace
    with active(session):
        assert "task-1" in tool["TaskCreate"]("check", "verify", "checking", "{}")
        tool["TaskUpdate"]("task-1", "completed", "", "", "")
        assert "completed" in tool["TaskList"]()
        assert "check" in tool["TaskGet"]("task-1")
        tool["TodoWrite"]('[{"content":"verify","status":"in_progress"}]')
        assert "in_progress" in str(tool["_CCPORT_TODOS"])
        assert tool["EnterPlanMode"]() == "Permission mode: plan"
        assert tool["ExitPlanMode"]() == "Permission mode: default"
        saved = json.loads(tool["Artifact"]("report", "hello artifact"))
        assert Path(saved["path"]).read_text() == "hello artifact"
        assert tool["ReviewArtifact"]("report") == "hello artifact"


@pytest.mark.integration
def test_live_web_tools_require_explicit_opt_in(workspace: Path) -> None:
    session = Session(workspace)
    with active(session):
        assert "Example" in session.namespace["WebFetch"]("https://example.com", "Read title")
