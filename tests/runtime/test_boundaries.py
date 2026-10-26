from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from src.runtime.run_state import RunConfig, RunStatus
from src.runtime.tool_dispatch import ToolOutcomeUnknown
from test_session import call, reply

from nexa_code.fixture_provider import FixtureProvider
from nexa_code.host import Host
from nexa_code.http_tools import request
from nexa_code.session import Session
from nexa_code.tool_services import active


@pytest.mark.parametrize("kind", ["message", "command", "resume"])
def test_cancel_received_before_worker_execution_is_retained(workspace: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    provider = FixtureProvider([reply("late")])
    session = Session(workspace, provider=provider)
    incoming: dict[str, Any] = {"type": kind, "request_id": "request", "content": "hello", "name": "/review", "session_id": session.id}
    if kind == "resume":
        provider.replies.insert(0, call("Write", {"file_path": "result", "content": "late"}))
        session.message("pending")
    requests_before = len(provider.requests)
    method = "resume" if kind == "resume" else "message"
    original = getattr(session, method)
    entered, release = threading.Event(), threading.Event()

    def scheduled(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    host = Host(session)
    monkeypatch.setattr(session, method, scheduled)
    try:
        host.handle(incoming)
        assert entered.wait(3)
        host.handle({"type": "cancel", "request_id": "cancel"})
        release.set()
        assert host.worker
        host.worker.join(3)
        assert session.state and session.state.status == RunStatus.CANCELLED
        assert len(provider.requests) == requests_before
        assert not (workspace / "result").exists()
    finally:
        release.set()
        host.close()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("stop", ["deadline", "cancel"])
def test_http_deadline_cancel_closes_inflight_operation(workspace: Path, monkeypatch: pytest.MonkeyPatch, method: str, stop: str) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    clock = [0.0]
    session.deadline = 1.0
    monkeypatch.setattr("nexa_code.http_tools.time", SimpleNamespace(monotonic=lambda: clock[0]))
    entered, closed = threading.Event(), threading.Event()

    async def delayed(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        try:
            await asyncio.sleep(10)
        finally:
            closed.set()

    monkeypatch.setattr(httpx.AsyncClient, "send", delayed)
    failures: list[Exception] = []

    def invoke() -> None:
        with active(session):
            try:
                request("https://offline.invalid/test", method=method)
            except RuntimeError as error:
                failures.append(error)

    worker = threading.Thread(target=invoke)
    worker.start()
    assert entered.wait(2)
    if stop == "cancel":
        session.request_cancel()
    else:
        clock[0] = session.deadline
    worker.join(2)
    assert not worker.is_alive()
    assert closed.is_set()
    assert len(failures) == 1
    assert isinstance(failures[0], ToolOutcomeUnknown if method == "POST" else RuntimeError)


def test_http_response_capture_is_bounded(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session(workspace, provider=FixtureProvider([]))

    async def response(client: httpx.AsyncClient, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 3_000_000, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", response)
    with active(session):
        result = request("https://offline.invalid/test", limit=1024)
    assert result["body"] == "x" * 1024


@pytest.mark.parametrize("tool", ["Grep", "CtxInspect"])
def test_search_processes_obey_run_deadline(workspace: Path, monkeypatch: pytest.MonkeyPatch, tool: str) -> None:
    arguments: dict[str, object] = (
        {}
        if tool == "CtxInspect"
        else {
            "pattern": "needle",
            "path": "",
            "glob": "",
            "output_mode": "content",
            "glob_type": "",
            "context_before": 0,
            "context_after": 0,
            "context_c": 0,
            "show_line_numbers": True,
            "case_insensitive": False,
            "head_limit": 10,
            "offset": 0,
            "multiline": False,
        }
    )
    session = Session(workspace, provider=FixtureProvider([call(tool, arguments)]), config=RunConfig(timeout=2))
    session.namespace["build_user_context"] = lambda model: "fixture context"
    fixture = workspace / "bin"
    fixture.mkdir()
    executable = fixture / ("rg" if tool == "Grep" else "git")
    executable.write_text("#!" + sys.executable + "\nimport os,time\nfrom pathlib import Path\nPath('pid').write_text(str(os.getpid()))\ntime.sleep(20)\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(fixture) + os.pathsep + os.environ["PATH"])
    started = time.monotonic()
    try:
        state = session.message("search")
        assert state.status == RunStatus.TIMED_OUT
        assert time.monotonic() - started < 4
        assert not session.jobs
        assert (workspace / "pid").exists(), "The fixture must execute to exercise process cancellation"
        with pytest.raises(ProcessLookupError):
            os.kill(int((workspace / "pid").read_text()), 0)
    finally:
        session.close()
