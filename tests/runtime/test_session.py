from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.runtime.providers import ModelReply
from src.runtime.run_state import RunConfig, RunStatus

from nexa_code.fixture_provider import FixtureProvider
from nexa_code.policy import Rule
from nexa_code.session import Session


def reply(text: str) -> ModelReply:
    return ModelReply({"role": "assistant", "content": text}, 10, 4, True)


def call(name: str, args: dict[str, object], ident: str = "call-1") -> ModelReply:
    return ModelReply(
        {"role": "assistant", "content": "", "tool_calls": [{"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
        10,
        2,
        True,
    )


def test_startup_definitions_and_two_turns(workspace: Path) -> None:
    provider = FixtureProvider([reply("one"), reply("two")])
    session = Session(workspace, provider=provider)
    first = session.message("first")
    second = session.message("second")
    assert first.success and second.success
    assert first.run_id != second.run_id
    assert second.metadata["parent_run_id"] == first.run_id
    users = [item["content"] for item in provider.requests[-1].messages if item["role"] == "user"]
    assert users[0].endswith("Current user request:\nfirst")
    assert users[1] == "second"
    assert len(session.agent.tools) >= 50
    assert session.usage()["input_tokens"] == 20


def test_write_approval_survives_restart_and_new_turn_does_not_inherit(workspace: Path) -> None:
    provider = FixtureProvider([call("Write", {"file_path": "hello.txt", "content": "hello"}), reply("done")])
    session = Session(workspace, provider=provider)
    state = session.message("write hello")
    assert state.status == RunStatus.WAITING_APPROVAL
    assert not (workspace / "hello.txt").exists()
    restored = Session(workspace, session_id=session.id, provider=provider)
    result = restored.approve(state.run_id, "call-1", "allow_once")
    assert result.success
    assert (workspace / "hello.txt").read_text() == "hello"
    assert result.approvals == {"call-1": True}
    assert restored.store.load(state.run_id).revision > state.revision


def test_deny_does_not_write_and_invalid_call_is_rejected(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([call("Write", {"file_path": "no.txt", "content": "x"}), reply("denied")]))
    state = session.message("write")
    with pytest.raises(ValueError):
        session.approve(state.run_id, "wrong", "allow_once")
    result = session.approve(state.run_id, "call-1", "deny")
    assert result.success
    assert not (workspace / "no.txt").exists()
    assert not result.tool_journal["call-1"]["success"]


def test_real_read_write_verification_command(workspace: Path) -> None:
    provider = FixtureProvider(
        [
            call("Write", {"file_path": "hello.txt", "content": "hello"}, "write"),
            call("Read", {"file_path": "hello.txt", "offset": 0, "limit": 0, "pages": ""}, "read"),
            call("Bash", {"command": 'test "$(cat hello.txt)" = hello && printf verified', "timeout": 5000, "run_in_background": False}, "check"),
            reply("verified"),
        ]
    )
    session = Session(workspace, provider=provider)
    state = session.message("write, read and verify")
    state = session.approve(state.run_id, "write", "allow_once")
    assert state.status == RunStatus.WAITING_APPROVAL
    state = session.approve(state.run_id, "check", "allow_once")
    assert state.success
    assert "hello" in state.tool_journal["read"]["content"]
    assert "verified" in state.tool_journal["check"]["content"]


def test_cancellation_timeout_budget_and_unknown_tool(workspace: Path) -> None:
    cancelled = Session(workspace, provider=FixtureProvider([reply("unused")]))
    cancelled.cancel.set()
    assert cancelled.message("cancel", reset_cancel=False).status == RunStatus.CANCELLED
    timeout = Session(workspace, provider=FixtureProvider([{"delay": 0.05, "text": "late"}]), config=RunConfig(timeout=0.01))
    assert timeout.message("timeout").status == RunStatus.TIMED_OUT
    budget = Session(workspace, provider=FixtureProvider([call("TaskList", {})]), config=RunConfig(max_tool_calls=0))
    assert budget.message("budget").status == RunStatus.BUDGET_EXHAUSTED
    unknown = Session(workspace, provider=FixtureProvider([call("DoesNotExist", {})]))
    assert unknown.message("unknown").status == RunStatus.FAILED


def test_unknown_outcome_blocks_continuation_until_operator_resolution(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([call("Write", {"file_path": "a", "content": "x"}), reply("resolved")]))
    state = session.message("write")
    state.tool_journal["call-1"] = {"status": "started", "tool": "Write"}
    state.status = RunStatus.FAILED
    session.save(state)
    with pytest.raises(ValueError, match="unknown"):
        session.message("continue")
    result = session.resolve(state.run_id, "call-1", "Operator verified no file was written", False)
    assert result.success
    assert not (workspace / "a").exists()


def test_legacy_import_is_validated_and_original_is_retained(workspace: Path) -> None:
    path = workspace / "old.jsonl"
    original = '{"role":"user","content":"old task"}\n{"role":"assistant","content":"old reply"}\n'
    path.write_text(original)
    session = Session(workspace, provider=FixtureProvider([reply("new")]))
    old_id = session.id
    imported = session.import_legacy(path)
    assert imported != old_id
    assert path.read_text() == original
    state = session.message("follow up")
    assert "Imported legacy transcript" in state.messages[1]["content"]
    assert state.metadata["legacy_source"] == str(path)
    path.write_text('{"role":"system","content":42}\n')
    with pytest.raises(ValueError, match="line 1"):
        session.import_legacy(path)


@pytest.mark.parametrize("switch", ["new", "resume", "import"])
def test_session_switch_resets_authorization_and_tool_state(workspace: Path, switch: str) -> None:
    session = Session(workspace, provider=FixtureProvider([reply("first"), reply("second")]))
    session.message("first")
    first = session.id
    session.new()
    session.message("second")
    session.policy.add(Rule.exact("Write", {"file_path": "a", "content": "x"}, workspace, "allow", "session"))
    session.set_mode("bypass", confirmed=True)
    session.namespace["_CCPORT_TASKS"] = {"task-1": {"subject": "must not leak"}}
    if switch == "new":
        session.new()
    elif switch == "resume":
        session.resume(first)
    else:
        path = workspace / "legacy.jsonl"
        path.write_text('{"role":"user","content":"legacy"}\n')
        session.import_legacy(path)
    assert session.policy.mode == "default"
    assert all(rule.scope != "session" for rule in session.policy.rules)
    assert not session.namespace.get("_CCPORT_TASKS")


def test_previous_run_metadata_and_disk_checkpoint_are_immutable(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([reply("first"), reply("second")]))
    session.namespace["_CCPORT_TASKS"] = {"task-1": {"status": "pending"}}
    first = session.message("first")
    saved = first.to_dict()
    disk = session.store.load(first.run_id).to_dict()
    session.namespace["_CCPORT_TASKS"]["task-1"]["status"] = "completed"
    session.artifact_names["report"] = "artifact-new"
    session.message("second")
    assert first.to_dict() == saved
    assert session.store.load(first.run_id).to_dict() == disk
    session.resume(session.id)
    assert session.state
    saved_current = session.state.to_dict()
    session.namespace["_CCPORT_TASKS"]["task-1"]["status"] = "changed"
    assert session.state.to_dict() == saved_current


def test_unknown_outcome_blocks_every_session_switch(workspace: Path) -> None:
    session = Session(workspace, provider=FixtureProvider([reply("first"), call("Write", {"file_path": "a", "content": "x"})]))
    session.message("first")
    first_id = session.id
    session.new()
    state = session.message("write")
    state.tool_journal["call-1"] = {"status": "started", "tool": "Write"}
    state.status = RunStatus.FAILED
    session.save(state)
    with pytest.raises(ValueError, match="unknown"):
        session.resume(first_id)
    with pytest.raises(ValueError, match="unknown"):
        session.new()
