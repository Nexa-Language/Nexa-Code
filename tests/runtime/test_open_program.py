from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from src.open_programs.model import (
    Candidate,
    CommandReport,
    CompilerEnvironment,
    ExecutionReport,
    ExecutionSpec,
    PatchValue,
    ProgramError,
    RepositoryCase,
    ResolutionBudget,
    RuntimeActivity,
    WorkspaceSnapshot,
)
from src.open_programs.protocol import AuthorActivity
from src.runtime.providers import ModelReply

from nexa_code.fixture_provider import FixtureProvider
from nexa_code.open_program import OpenConfig, OpenProgram
from nexa_code.open_source import SourceSync, checked, intent_source

IMAGE = "python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
SOURCE = 'language "3.0"\nprogram Demo { goal answer() -> Int { stage runtime intent "Return an answer" implementation open } }\n'


class LiteralExecutor:
    def execute_candidate(self, candidate: Candidate, spec: ExecutionSpec) -> ExecutionReport:
        return ExecutionReport(succeeded=True, output_json=candidate.implementation.body, exit_code=0)

    def execute_repository(self, base: WorkspaceSnapshot, patch: PatchValue, case: RepositoryCase, spec: ExecutionSpec) -> CommandReport:
        raise AssertionError("Unexpected repository execution")


def program(tmp_path: Path, replies: list[ModelReply | dict[str, Any]] | None = None) -> OpenProgram:
    source = tmp_path / "demo.nx"
    source.write_text(SOURCE)
    environment = tmp_path / "environment.json"
    environment.write_text(CompilerEnvironment(image=IMAGE, allow_model=True, model="fixture").model_dump_json())
    return OpenProgram(
        OpenConfig(source=source, environment=environment, state=tmp_path / "state.db", program_id="demo", workspace=tmp_path),
        provider=FixtureProvider(replies or []),
        executor=LiteralExecutor(),
    )


def test_offline_check_build_and_restart_keep_separate_revisions(tmp_path: Path) -> None:
    client = program(tmp_path)
    try:
        report = client.check()
        assert report.ok and report.obligations == ("answer",)
        head = client.build(expected_revision=None, source_digest=report.source_digest)
        assert client.status()["active_revision"] == head.revision
        assert client.status()["source_revision"] == head.revision
        assert isinstance(client.compiler.provider, FixtureProvider) and not client.compiler.provider.requests
        resumed = OpenProgram(client.config, provider=FixtureProvider([]), executor=LiteralExecutor())
        try:
            assert resumed.status()["active_revision"] == head.revision
            assert resumed.build(expected_revision=head.revision, source_digest=report.source_digest, locked=True) == head
            assert isinstance(resumed.compiler.provider, FixtureProvider) and not resumed.compiler.provider.requests
        finally:
            resumed.close()
    finally:
        client.close()


def test_exact_cancel_reads_native_activity_after_restart(tmp_path: Path) -> None:
    client = program(tmp_path)
    try:
        client.build(expected_revision=None, source_digest=client.check().source_digest)
        first = client.session.runtime.start_activity("demo", "answer")
        second = client.session.runtime.start_activity("demo", "answer")
        restarted = OpenProgram(client.config, provider=FixtureProvider([]), executor=LiteralExecutor())
        try:
            assert {item.activity_id for item in restarted.runtime_activities()} == {first.activity_id, second.activity_id}
            assert restarted.cancel(second.activity_id, domain="runtime").state == "cancelled"
            assert restarted.session.runtime.activity(first.activity_id).state == "pending"
            foreign = RuntimeActivity(activity_id="foreign", program_id="other", revision=first.revision, artifact_digest=first.artifact_digest, goal="answer")
            client.store.set_reference("runtime.activity:foreign", None, foreign)
            with pytest.raises(ProgramError, match="program_mismatch"):
                restarted.cancel("foreign", domain="runtime")
        finally:
            restarted.close()
    finally:
        client.close()


def wait_author(client: OpenProgram, identifier: str) -> AuthorActivity:
    end = time.monotonic() + 3
    while time.monotonic() < end:
        activity = client.author_activity(identifier)
        if activity.state != "running":
            return activity
        time.sleep(0.01)
    raise AssertionError("Author activity did not finish")


def test_clarification_survives_restart_source_confirmation_build_and_run(tmp_path: Path) -> None:
    client = program(tmp_path, [{"text": json.dumps({"clarification": "Which answer?"})}])
    source = client.check().source_digest
    revision = client.propose_source(expected_revision=None, source_digest=source)
    activity = wait_author(client, client.author_resolve("answer", expected_revision=revision, source_digest=source))
    assert activity.result and activity.result.clarification == "Which answer?"
    pending = client.answer(activity.request_id, "Return 42", expected_revision=revision, source_digest=source)
    assert "Author clarification: Return 42" in pending.diff
    assert client.config.source.read_text() == SOURCE
    client.close()
    restarted = OpenProgram(
        client.config, provider=FixtureProvider([{"text": json.dumps({"implementation": {"kind": "value", "body": "42"}})}]), executor=LiteralExecutor()
    )
    try:
        with pytest.raises(ProgramError, match="source_sync_pending"):
            restarted.build(expected_revision=pending.revision, source_digest=source)
        restarted.sync_source(pending.digest, confirmed=True)
        report = restarted.check()
        assert report.program and report.program.goals[0].intent.endswith("Author clarification: Return 42")
        head = restarted.build(expected_revision=restarted.status()["source_revision"], source_digest=report.source_digest)
        identifier, result = restarted.run_goal("answer", expected_revision=head.revision, source_digest=report.source_digest)
        assert result.status == "accepted" and result.output_json == "42"
        assert restarted.session.runtime.activity(identifier).revision == head.revision
    finally:
        restarted.close()


def test_source_cas_and_rejected_sync_preserve_user_edit(tmp_path: Path) -> None:
    client = program(tmp_path, [{"text": json.dumps({"clarification": "Which answer?"})}])
    try:
        source = client.check().source_digest
        revision = client.propose_source(expected_revision=None, source_digest=source)
        with pytest.raises(ProgramError, match="revision_conflict"):
            client.build(expected_revision="stale", source_digest=source)
        activity = wait_author(client, client.author_resolve("answer", expected_revision=revision, source_digest=source))
        pending = client.answer(activity.request_id, "42", expected_revision=revision, source_digest=source)
        client.sync_source(pending.digest, confirmed=False)
        client.config.source.write_text(SOURCE + "// user edit\n")
        rejected = client.source_sync.pending()
        assert rejected is not None
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(rejected.digest, confirmed=True)
        assert client.config.source.read_text().endswith("// user edit\n")
        with pytest.raises(ProgramError, match="source_sync_pending"):
            client.build(expected_revision=pending.revision, source_digest=client.check().source_digest)
    finally:
        client.close()


def test_zero_budget_is_explicit_and_cannot_use_legacy_approval(tmp_path: Path) -> None:
    client = program(tmp_path)
    try:
        head = client.build(expected_revision=None, source_digest=client.check().source_digest)
        _, result = client.run_goal(
            "answer", expected_revision=head.revision, source_digest=client.check().source_digest, budget=ResolutionBudget(max_model_calls=0)
        )
        assert result.status == "blocked" and result.model_calls == 0
        with pytest.raises(ProgramError):
            client.apply("legacy-call", "allow_session")
    finally:
        client.close()


def test_external_author_answer_without_local_journal_blocks_source_overwrite(tmp_path: Path) -> None:
    client = program(tmp_path, [{"text": json.dumps({"clarification": "Which answer?"})}])
    try:
        source = client.check().source_digest
        revision = client.propose_source(expected_revision=None, source_digest=source)
        activity = wait_author(client, client.author_resolve("answer", expected_revision=revision, source_digest=source))
        response = client.author.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "author/answer",
                "params": {
                    "program_id": "demo",
                    "expected_revision": revision,
                    "request_id": activity.request_id,
                    "answer": "external answer",
                },
            }
        )
        assert response and "result" in response
        current = client.store.current_revision("demo")
        assert current and client.source_sync.pending() is None
        for operation in (client.build, client.propose_source):
            with pytest.raises(ProgramError, match="source_sync_pending"):
                operation(expected_revision=current.digest, source_digest=source)
        assert client.config.source.read_text() == SOURCE
    finally:
        client.close()


@pytest.mark.parametrize("boundary", ["prepared", "answer", "source_write", "revision_commit"])
@pytest.mark.parametrize("reject_before_confirmation", [False, True])
def test_source_sync_restarts_at_each_persistence_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str, reject_before_confirmation: bool
) -> None:
    client = program(tmp_path, [{"text": json.dumps({"clarification": "Which answer?"})}])
    source = client.check().source_digest
    revision = client.propose_source(expected_revision=None, source_digest=source)
    activity = wait_author(client, client.author_resolve("answer", expected_revision=revision, source_digest=source))
    original_reference, original_commit = client.store.set_reference, client.store.commit_revision

    def reference(name: str, expected: str | None, record: Any, **kwargs: Any) -> str:
        if boundary == "answer" and isinstance(record, SourceSync) and record.state == "pending":
            raise SystemExit("process died after author answer")
        result = original_reference(name, expected, record, **kwargs)
        if boundary == "prepared" and isinstance(record, SourceSync) and record.state == "prepared":
            raise SystemExit("process died before author answer")
        return result

    def commit(expected: str | None, record: Any, events: Any) -> str:
        if events[0].kind == "source_synchronized":
            if boundary == "source_write":
                raise SystemExit("process died after source write")
            result = original_commit(expected, record, events)
            if boundary == "revision_commit":
                raise SystemExit("process died after revision commit")
            return result
        return original_commit(expected, record, events)

    monkeypatch.setattr(client.store, "set_reference", reference)
    monkeypatch.setattr(client.store, "commit_revision", commit)
    with pytest.raises(SystemExit):
        pending = client.answer(activity.request_id, "42", expected_revision=revision, source_digest=source)
        client.sync_source(pending.digest, confirmed=True)
    client.close()
    restarted = OpenProgram(client.config, provider=FixtureProvider([]), executor=LiteralExecutor())
    try:
        pending = restarted.source_sync.pending()
        assert pending
        if reject_before_confirmation:
            pending = restarted.sync_source(pending.digest, confirmed=False)
            assert pending.state == "rejected"
        restarted.sync_source(pending.digest, confirmed=True)
        assert restarted.source_sync.pending() is None
        report = restarted.check()
        assert report.program and report.program.goals[0].intent.endswith("Author clarification: 42")
        assert sum(event.kind == "author_answered" for _, event in restarted.store.events("demo")) == 1
    finally:
        restarted.close()


def test_concurrent_runtime_activation_cannot_execute_unselected_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = program(tmp_path)
    try:
        head = client.build(expected_revision=None, source_digest=client.check().source_digest)
        run = client.session.run_goal

        def interleaved(program_id: str, goal: str, **kwargs: Any) -> Any:
            client.config.source.write_text(SOURCE.replace("Return an answer", "Concurrent revision"))
            client.session.activate(client.config.source, program_id="demo", expected_revision=head.revision)
            return run(program_id, goal, **kwargs)

        monkeypatch.setattr(client.session, "run_goal", interleaved)
        with pytest.raises(ProgramError, match="revision_conflict"):
            client.run_goal("answer", expected_revision=head.revision, source_digest=client.check().source_digest)
        assert isinstance(client.compiler.provider, FixtureProvider) and not client.compiler.provider.requests
        assert all(activity.state == "cancelled" for activity in client.runtime_activities())
    finally:
        client.close()


def test_build_uses_the_checked_source_when_editor_changes_during_activation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = program(tmp_path)
    activate = client.session.activate
    captured: list[str] = []

    def interleaved(path: Path, **kwargs: Any) -> Any:
        client.config.source.write_text(SOURCE.replace("Return an answer", "Unreviewed edit"))
        captured.append(path.read_text())
        return activate(path, **kwargs)

    monkeypatch.setattr(client.session, "activate", interleaved)
    try:
        with pytest.raises(ProgramError, match="source_conflict"):
            client.build(expected_revision=None, source_digest=client.check().source_digest)
        assert captured == [SOURCE]
        assert "Unreviewed edit" in client.config.source.read_text()
    finally:
        client.close()


def test_resume_keeps_unknown_external_effect_blocking_execution(tmp_path: Path) -> None:
    client = program(tmp_path)
    try:
        head = client.build(expected_revision=None, source_digest=client.check().source_digest)
        effect = client.session.runtime.effects.prepare("demo", "remote-write", "payload", idempotent=False)

        def lost_response(operation_id: str) -> str:
            raise ConnectionError("response lost")

        with pytest.raises(ConnectionError):
            client.session.runtime.effects.execute(effect.operation_id, lost_response)
        client.resume()
        assert client.status()["effects"][0]["state"] == "unknown"
        with pytest.raises(ProgramError, match="pending_effect"):
            client.run_goal("answer", expected_revision=head.revision, source_digest=client.check().source_digest)
    finally:
        client.close()


def test_author_resolve_requires_the_checked_source_to_match_the_selected_draft(tmp_path: Path) -> None:
    client = program(tmp_path, [{"text": json.dumps({"clarification": "Which answer?"})}])
    try:
        revision = client.propose_source(expected_revision=None, source_digest=client.check().source_digest)
        client.config.source.write_text(SOURCE.replace("Return an answer", "Current edited intent"))
        digest = client.check().source_digest
        with pytest.raises(ProgramError, match="source_draft_mismatch"):
            client.author_resolve("answer", expected_revision=revision, source_digest=digest)
        assert not client.author_activities()
        assert isinstance(client.compiler.provider, FixtureProvider) and not client.compiler.provider.requests
        updated = client.propose_source(expected_revision=revision, source_digest=digest)
        client.config.source.write_text("// Formatting does not change the selected semantics\n" + client.config.source.read_text())
        activity = wait_author(client, client.author_resolve("answer", expected_revision=updated, source_digest=client.check().source_digest))
        assert activity.revision == updated
        assert "Current edited intent" in str(client.compiler.provider.requests)
    finally:
        client.close()


@pytest.mark.parametrize("operation", ["build", "locked", "run", "maintain", "author", "inspect", "approve", "apply", "resume"])
def test_environment_drift_blocks_native_operation_boundaries(tmp_path: Path, operation: str) -> None:
    client = program(tmp_path)
    try:
        digest = client.check().source_digest
        head = client.build(expected_revision=None, source_digest=digest)
        environment = json.loads(client.config.environment.read_text())
        environment["capabilities"] = []
        client.config.environment.write_text(json.dumps(environment))
        actions = {
            "build": lambda: client.build(expected_revision=head.revision, source_digest=digest),
            "locked": lambda: client.build(expected_revision=head.revision, source_digest=digest, locked=True),
            "run": lambda: client.run_goal("answer", expected_revision=head.revision, source_digest=digest),
            "maintain": lambda: client.maintain(["x.py"], "Fix", expected_revision=head.revision, source_digest=digest),
            "author": lambda: client.author_resolve("answer", expected_revision=head.revision, source_digest=digest),
            "inspect": lambda: client.inspect_proposal("missing"),
            "approve": lambda: client.approve("missing", actor="review", confirmed=True),
            "apply": lambda: client.apply("missing", "missing"),
            "resume": client.resume,
        }
        with pytest.raises(ProgramError, match="environment_changed"):
            actions[operation]()
        assert client.status()["active_revision"] == head.revision
        assert isinstance(client.compiler.provider, FixtureProvider) and not client.compiler.provider.requests
        assert not client.runtime_activities() and not client.author_activities()
    finally:
        client.close()


def test_environment_reformatting_is_allowed_and_invalid_file_blocks_execution(tmp_path: Path) -> None:
    client = program(tmp_path)
    try:
        digest = client.check().source_digest
        environment = json.loads(client.config.environment.read_text())
        client.config.environment.write_text(json.dumps(environment, indent=4, sort_keys=True))
        head = client.build(expected_revision=None, source_digest=digest)
        client.config.environment.write_text("{invalid")
        with pytest.raises(ProgramError, match="environment_unavailable"):
            client.build(expected_revision=head.revision, source_digest=digest, locked=True)
        assert client.status()["active_revision"] == head.revision
    finally:
        client.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("image", "python@sha256:" + "a" * 64),
        ("model", "different-fixture"),
        ("allow_model", False),
        ("dependencies", [{"name": "dataset", "digest": "changed"}]),
        ("provider", {"protocol": "chat", "base_url_env": "NEXA_TEST_SOURCE_ENDPOINT", "api_key_env": "NEXA_TEST_UNUSED_KEY"}),
    ],
)
def test_environment_guard_compares_all_native_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any) -> None:
    client = program(tmp_path)
    try:
        monkeypatch.setenv("NEXA_TEST_SOURCE_ENDPOINT", "https://fixture.invalid/v1")
        environment = json.loads(client.config.environment.read_text())
        environment[field] = value
        client.config.environment.write_text(json.dumps(environment))
        with pytest.raises(ProgramError, match="environment_changed"):
            client.build(expected_revision=None, source_digest=client.check().source_digest)
        assert client.store.current_revision("demo") is None
        assert isinstance(client.compiler.provider, FixtureProvider) and not client.compiler.provider.requests
    finally:
        client.close()


@pytest.mark.parametrize("field", ['intent "Return 1"', 'intent // Intent field comment\n "Return 1"'])
def test_intent_sync_distinguishes_parameter_names_and_skips_comments(tmp_path: Path, field: str) -> None:
    text = 'language "3.0"\nprogram Demo { goal answer(intent: String) -> Int { stage runtime ' + field + " implementation open } }\n"
    path = tmp_path / "demo.nx"
    before = checked(text, path).program
    assert before is not None
    goal = before.goals[0].model_copy(update={"intent": "Return 1\nAuthor clarification: 1"})
    after = before.model_copy(update={"goals": (goal,)})
    updated = intent_source(text, path, before, after)
    result = checked(updated, path).program
    assert result is not None and result.digest == after.digest
    assert "answer(intent: String)" in updated
    if "//" in field:
        assert "// Intent field comment" in updated
