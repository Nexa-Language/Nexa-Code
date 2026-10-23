from __future__ import annotations

import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path

import pytest
from test_session import call, reply

from nexa_code.commands import run_command
from nexa_code.fixture_provider import FixtureProvider
from nexa_code.loader import APP_ROOT
from nexa_code.processes import CAPTURE_LIMIT, run, start
from nexa_code.session import Session
from nexa_code.tool_services import active


def test_cleanup_failure_publishes_completion(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexa_code import processes

    session = Session(workspace, provider=FixtureProvider([]))
    terminate = processes.terminate

    def fail_after_cleanup(process: processes.subprocess.Popen[str]) -> None:
        terminate(process)
        raise RuntimeError("fixture cleanup error")

    monkeypatch.setattr(processes, "terminate", fail_after_cleanup)
    job = start(session, [sys.executable, "-c", "import time; time.sleep(20)"], timeout=0.1)
    assert job.done.wait(timeout=3)
    assert job.status == "cleanup_failed"
    assert job.process.poll() is not None
    assert session.close() is False


def test_invalid_question_fails_before_emitting_ui_event(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    with active(session), pytest.raises(ValueError, match="options"):
        session.namespace["AskUserQuestion"]('[{"question":"Pick", "options":{}}]')


def test_benchmark_adapter_uses_protocol_fixture(workspace: Path) -> None:
    from run_harness_bench import run_task

    fixture = workspace / "fixture.json"
    fixture.write_text(json.dumps([{"text": "offline bench result"}]))
    result = run_task(workspace, "hello", timeout=10, allow_tools=False, fixture=fixture)
    assert result["status"] == "completed"
    assert result["reply"] == "offline bench result"


def test_background_deadline_drain_and_output_bound(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    try:
        timed = start(session, [sys.executable, "-c", "import time; time.sleep(20)"], timeout=0.1)
        assert timed.done.wait(timeout=2)
        assert timed.status == "timed_out"
        assert timed.process.poll() is not None
        output = start(session, [sys.executable, "-c", "import sys;sys.stdout.write('x'*2000000);sys.stderr.write('y'*2000000)"], timeout=5)
        assert output.done.wait(timeout=3)
        assert output.status == "completed"
        assert len(str(output.result()["stdout"])) < CAPTURE_LIMIT + 100
        assert "truncated" in str(output.result()["stderr"])
        cancelled = start(session, [sys.executable, "-c", "import time; time.sleep(20)"], timeout=30)
        session.cancel.set()
        assert cancelled.done.wait(timeout=2)
        assert cancelled.status == "cancelled"
    finally:
        session.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group contract")
def test_redirected_descendants_are_reaped_after_leader_exit(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    job = start(session, ["/bin/bash", "-c", "sleep 30 >/dev/null 2>&1 & echo $!"], timeout=5)
    try:
        assert job.done.wait(timeout=3)
        child = int(str(job.result()["stdout"]).strip())
        assert job.error is None, "".join(traceback.format_exception(job.error)) if job.error else ""
        assert session.close()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            pytest.fail("Redirected descendant survived managed process cleanup")
    finally:
        try:
            os.killpg(job.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_repl_command_and_child_usage_use_same_runtime(workspace: Path) -> None:
    provider = FixtureProvider([call("Agent", {"subagent_type": "explore", "prompt": "inspect", "description": "research"}), reply("child"), reply("parent")])
    session = Session(workspace, provider=provider)
    state = session.message("research")
    state = session.approve(state.run_id, "call-1", "allow_once")
    assert state.success
    assert session.usage()["model_calls"] == 3
    assert len(session.catalog.runs(session.id)) == 1
    assert len(session.catalog.runs(session.id, include_children=True)) == 2
    restored = Session(workspace, session_id=session.id, provider=FixtureProvider([]))
    assert restored.state and restored.state.run_id == state.run_id
    with active(session):
        output = json.loads(session.namespace["REPL"]("print(6*7)"))
    assert output["stdout"].strip() == "42"
    assert run(session, [sys.executable, "-c", "print('check')"])["exit_code"] == 0


def test_settings_are_validated_loaded_and_plan_blocks_shell_commands(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([]))
    run_command(session, "/config set max_tool_calls 7")
    run_command(session, '/config set theme "light"')
    assert Session(workspace, provider=FixtureProvider([])).config.max_tool_calls == 7
    with pytest.raises(ValueError):
        run_command(session, "/config set timeout -2")
    with pytest.raises(ValueError):
        run_command(session, "/config set auto_commit true")
    session.set_mode("plan")
    with pytest.raises(PermissionError):
        run_command(session, "/git branch -D important")
    with pytest.raises(PermissionError):
        run_command(session, "/diff --output=changed")


def test_mcp_stdio_tools_resources_and_cleanup(workspace: Path) -> None:
    pytest.importorskip("mcp", reason="Install uv sync --extra mcp for the offline MCP suite")
    pid_path = workspace / "mcp.pid"
    (workspace / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fixture": {
                        "command": sys.executable,
                        "args": [str(APP_ROOT / "tests" / "fixtures" / "mcp_server.py")],
                        "env": {"NEXA_MCP_PID": str(pid_path)},
                    }
                }
            }
        )
    )
    session = Session(workspace, provider=FixtureProvider([]))
    with active(session):
        assert "fixture:hello" in session.namespace["MCPTool"]("fixture", "echo", '{"value":"hello"}')
        assert "note://hello" in session.namespace["ListMcpResources"]("fixture")
        assert "fixture resource" in session.namespace["ReadMcpResource"]("fixture", "note://hello")
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)
