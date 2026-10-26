from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from src.open_programs.model import ProgramError
from src.open_programs.store import ProgramStore
from test_open_program import SOURCE, LiteralExecutor, program, wait_author

from nexa_code.fixture_provider import FixtureProvider
from nexa_code.open_program import OpenConfig, OpenProgram
from nexa_code.open_source import SourceSync

ROOT = Path(__file__).resolve().parents[2]
EDIT = "// Concurrent editor content\n" + SOURCE


def pending_sync(client: OpenProgram) -> SourceSync:
    digest = client.check().source_digest
    revision = client.propose_source(expected_revision=None, source_digest=digest)
    activity = wait_author(client, client.author_resolve("answer", expected_revision=revision, source_digest=digest))
    return client.answer(activity.request_id, "42", expected_revision=revision, source_digest=digest)


def crash_child(root: Path, boundary: str, edit: str) -> None:
    client = program(root, [{"text": json.dumps({"clarification": "Which answer?"})}])
    pending = pending_sync(client)
    (root / "pending.json").write_text(pending.model_dump_json())
    (root / "replies.json").write_text("[]")
    original_rename, original_link = os.rename, os.link
    original_reference, original_commit = client.store.set_reference, client.store.commit_revision
    retained_handle = client.config.source.open("r+")

    def edit_original() -> None:
        retained_handle.seek(0)
        retained_handle.write(EDIT)
        retained_handle.truncate()
        retained_handle.flush()
        os.fsync(retained_handle.fileno())

    def rename(source: Any, destination: Any, **kwargs: Any) -> None:
        if edit == "before_rename":
            client.config.source.write_text(EDIT)
        original_rename(source, destination, **kwargs)
        if edit == "after_rename":
            client.config.source.write_text(EDIT)
        if boundary == "rename":
            os._exit(71)

    def link(source: Any, destination: Any, **kwargs: Any) -> None:
        original_link(source, destination, **kwargs)
        if boundary == "link":
            if edit == "old_fd":
                edit_original()
            os._exit(71)

    def reference(name: str, expected: str | None, record: Any, **kwargs: Any) -> str:
        result = original_reference(name, expected, record, **kwargs)
        if type(record).__name__ == "SourceWriteIntent" and getattr(record, "phase", "") == boundary:
            os._exit(71)
        return result

    def commit(expected: str | None, record: Any, events: Any) -> str:
        result = original_commit(expected, record, events)
        if boundary == "revision" and events[0].kind == "source_synchronized":
            if edit == "old_fd":
                edit_original()
            os._exit(71)
        return result

    patch = pytest.MonkeyPatch()
    patch.setattr(os, "rename", rename)
    patch.setattr(os, "link", link)
    patch.setattr(client.store, "set_reference", reference)
    patch.setattr(client.store, "commit_revision", commit)
    client.sync_source(pending.digest, confirmed=True)
    raise AssertionError("Selected crash boundary was not reached")


def run_crash(root: Path, boundary: str, edit: str = "none") -> SourceSync:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), str(root), boundary, edit], cwd=ROOT, capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 71, result.stdout + result.stderr
    return SourceSync.model_validate_json((root / "pending.json").read_text())


def start_host(root: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "nexa_code.host",
            "--cwd",
            str(root),
            "--program",
            "demo.nx",
            "--environment",
            "environment.json",
            "--state",
            "state.db",
            "--fixture",
            "replies.json",
        ],
        cwd=ROOT,
        input='{"version":1,"type":"exit"}\n',
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0, result.stdout + result.stderr
    assert events[0]["type"] == "open_ready", events
    assert events[-1]["type"] == "session_end" and events[-1]["clean"]
    return events[0]["snapshot"]


def reopen(root: Path) -> OpenProgram:
    return OpenProgram(
        OpenConfig(root / "demo.nx", root / "environment.json", root / "state.db", "demo", root), provider=FixtureProvider([]), executor=LiteralExecutor()
    )


@pytest.mark.parametrize("boundary", ["prepared", "staged", "rename", "link", "revision"])
def test_internal_source_write_process_death_recovers_through_normal_host(root: Path, boundary: str) -> None:
    pending = run_crash(root, boundary)
    snapshot = start_host(root)
    assert snapshot["pending_sync"]["sync_id"] == pending.digest
    client = reopen(root)
    try:
        client.sync_source(pending.digest, confirmed=True)
        assert client.source_sync.pending() is None
        assert client.config.source.read_text() == pending.source
        assert client.status()["source_recovery"]
        assert client.check().program is not None
    finally:
        client.close()
    assert start_host(root)["pending_sync"] is None


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.parametrize(("boundary", "edit"), [("rename", "before_rename"), ("rename", "after_rename"), ("link", "old_fd")])
def test_interrupted_source_write_preserves_concurrent_editor_content(root: Path, boundary: str, edit: str) -> None:
    pending = run_crash(root, boundary, edit)
    snapshot = start_host(root)
    assert snapshot["pending_sync"]["sync_id"] == pending.digest
    paths = [root / "demo.nx", *(Path(item["original_path"]) for item in snapshot["source_recovery"])]
    assert any(path.exists() and path.read_text() == EDIT for path in paths)
    before = {path: path.read_bytes() for path in paths if path.exists()}
    client = reopen(root)
    try:
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(pending.digest, confirmed=True)
        assert {path: path.read_bytes() for path in before} == before
    finally:
        client.close()


def test_successful_sync_retains_original_inode_for_late_editor_write(root: Path) -> None:
    client = program(root, [{"text": json.dumps({"clarification": "Which answer?"})}])
    try:
        pending = pending_sync(client)
        with client.config.source.open("r+") as editor:
            client.sync_source(pending.digest, confirmed=True)
            editor.seek(0)
            editor.write(EDIT)
            editor.truncate()
            editor.flush()
        assert client.config.source.read_text() == pending.source
        paths = [Path(item["original_path"]) for item in client.status()["source_recovery"]]
        assert any(path.read_text() == EDIT for path in paths if path.exists())
    finally:
        client.close()


def test_clarification_preserves_crlf_bytes_outside_the_intent(root: Path) -> None:
    client = program(root, [{"text": json.dumps({"clarification": "Which answer?"})}])
    original = SOURCE.replace("\n", "\r\n").encode()
    client.config.source.write_bytes(original)
    try:
        pending = pending_sync(client)
        assert pending.base_source.encode() == original
        client.sync_source(pending.digest, confirmed=True)
        expected = original.replace(b'"Return an answer"', b'"Return an answer\\nAuthor clarification: 42"')
        assert client.config.source.read_bytes() == expected
        assert client.check().source_digest == pending.source_digest
    finally:
        client.close()


def test_legacy_source_sync_serialized_identity_remains_readable(root: Path) -> None:
    fixture = json.loads((ROOT / "tests/fixtures/open-programs/source-sync-v1.json").read_text())
    store = ProgramStore(root / "legacy.db")
    with sqlite3.connect(store.path) as connection:
        connection.execute("INSERT INTO objects VALUES (?, 'SourceSync', ?)", (fixture["digest"], json.dumps(fixture["record"])))
        connection.execute("INSERT INTO refs VALUES ('legacy-sync', ?)", (fixture["digest"],))
    record = store.reference("legacy-sync", SourceSync)
    assert record and record.digest == fixture["digest"] and record.state == "pending"


def test_rejecting_conflicted_sync_cannot_hide_a_retained_concurrent_edit(root: Path) -> None:
    pending = run_crash(root, "link", "old_fd")
    start_host(root)
    client = reopen(root)
    try:
        rejected = client.sync_source(pending.digest, confirmed=False)
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(rejected.digest, confirmed=True)
    finally:
        client.close()


def test_committed_revision_recovery_preserves_retained_conflict_after_reconfirm(root: Path) -> None:
    pending = run_crash(root, "revision", "old_fd")
    snapshot = start_host(root)
    assert snapshot["pending_sync"]["sync_id"] == pending.digest
    assert [item["state"] for item in snapshot["source_recovery"]] == ["conflict"]
    paths = [root / "demo.nx", *(Path(item["original_path"]) for item in snapshot["source_recovery"])]
    before = {path: path.read_bytes() for path in paths}
    assert before[root / "demo.nx"] == pending.source.encode()
    assert any(content == EDIT.encode() for content in before.values())
    client = reopen(root)
    try:
        current = client.store.current_revision("demo")
        assert current and current.parent == pending.revision
        rejected = client.sync_source(pending.digest, confirmed=False)
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(rejected.digest, confirmed=True)
        assert client.source_sync.pending() == rejected
        assert [item["state"] for item in client.status()["source_recovery"]] == ["conflict"]
        assert {path: path.read_bytes() for path in before} == before
    finally:
        client.close()
    restarted = start_host(root)
    assert restarted["pending_sync"]["sync_id"] == rejected.digest
    assert [item["state"] for item in restarted["source_recovery"]] == ["conflict"]


def test_revision_commit_rechecks_retained_edit_before_completing_sync(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = program(root, [{"text": json.dumps({"clarification": "Which answer?"})}])
    try:
        pending = pending_sync(client)
        original_commit = client.store.commit_revision
        with client.config.source.open("r+") as editor:

            def commit(expected: str | None, record: Any, events: Any) -> str:
                result = original_commit(expected, record, events)
                if events[0].kind == "source_synchronized":
                    editor.seek(0)
                    editor.write(EDIT)
                    editor.truncate()
                    editor.flush()
                    os.fsync(editor.fileno())
                return result

            monkeypatch.setattr(client.store, "commit_revision", commit)
            with pytest.raises(ProgramError, match="source_conflict"):
                client.sync_source(pending.digest, confirmed=True)
        assert client.source_sync.pending() == pending
        assert client.config.source.read_bytes() == pending.source.encode()
        recovery = client.status()["source_recovery"]
        assert [item["state"] for item in recovery] == ["conflict"]
        assert Path(recovery[0]["original_path"]).read_bytes() == EDIT.encode()
    finally:
        client.close()


def test_source_recovery_never_replaces_a_concurrently_recreated_target(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pending = run_crash(root, "rename")
    original = os.link

    def interleaved(*args: Any, **kwargs: Any) -> None:
        (root / "demo.nx").write_text(EDIT)
        original(*args, **kwargs)

    monkeypatch.setattr(os, "link", interleaved)
    client = reopen(root)
    try:
        assert client.status()["source_recovery"][0]["state"] == "conflict"
        assert client.config.source.read_text() == EDIT
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(pending.digest, confirmed=True)
        assert client.config.source.read_text() == EDIT
    finally:
        client.close()


def test_source_recovery_preserves_a_replacement_symlink(root: Path) -> None:
    pending = run_crash(root, "rename")
    other = root / "user-edit.nx"
    other.write_text(EDIT)
    (root / "demo.nx").symlink_to(other)
    client = reopen(root)
    try:
        assert client.status()["source_recovery"][0]["state"] == "conflict"
        with pytest.raises(ProgramError, match="source_conflict"):
            client.sync_source(pending.digest, confirmed=True)
        assert client.config.source.is_symlink() and other.read_text() == EDIT
    finally:
        client.close()


if __name__ == "__main__":
    crash_child(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
