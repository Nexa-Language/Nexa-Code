from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest
from test_open_program import IMAGE, SOURCE

ROOT = Path(__file__).resolve().parents[2]


class NativeClient:
    def __init__(self, workspace: Path, replies: list[dict[str, Any]] | None = None) -> None:
        source, environment, fixture = workspace / "demo.nx", workspace / "environment.json", workspace / "replies.json"
        if not source.exists():
            source.write_text(SOURCE)
        environment.write_text(json.dumps({"image": IMAGE, "allow_model": True, "model": "fixture"}))
        fixture.write_text(json.dumps(replies or []))
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "nexa_code.host",
                "--cwd",
                str(workspace),
                "--program",
                "demo.nx",
                "--environment",
                "environment.json",
                "--state",
                "state.db",
                "--program-id",
                "demo",
                "--fixture",
                str(fixture),
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.observed: list[dict[str, Any]] = []
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.ready = self.wait("open_ready")

    def _read(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            value = json.loads(line)
            self.observed.append(value)
            self.events.put(value)

    def wait(self, kind: str) -> dict[str, Any]:
        while True:
            try:
                value = self.events.get(timeout=10)
            except queue.Empty as error:
                raise AssertionError(f"Missing {kind}; events={self.observed}") from error
            if value["type"] == kind:
                return value
            assert value["type"] != "error", value

    def send(self, kind: str, **payload: Any) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(
            json.dumps({"version": 1, "type": kind, "request_id": uuid.uuid4().hex, **({"program_id": "demo"} if kind.startswith("open_") else {}), **payload})
            + "\n"
        )
        self.proc.stdin.flush()

    def close(self) -> None:
        try:
            if self.proc.poll() is None:
                self.send("exit")
                assert self.wait("session_end")["clean"]
                assert self.proc.wait(timeout=5) == 0
        finally:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=5)
            self.reader.join(timeout=1)
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                assert stream
                stream.close()


def test_native_host_restart_invalid_frames_and_legacy_approval_isolation(tmp_path: Path) -> None:
    client = NativeClient(tmp_path)
    try:
        source = client.ready["snapshot"]["source_digest"]
        client.send("open_build", source_digest=source, expected_revision=None)
        status = client.wait("open_status")
        client.wait("request_completed")
        revision = status["active_revision"]
        client.send("approve", run_id="legacy", call_id="call", decision="allow_once")
        assert "native" in client.wait("error")["message"]
        client.wait("request_completed")
        client.send("open_run", source_digest=source, expected_revision=None, goal="answer")
        assert client.wait("error")["code"] == "ProtocolError"
        client.wait("request_completed")
        client.send("open_build", source_digest=source, expected_revision="stale")
        assert client.wait("error")["code"] == "revision_conflict"
        client.wait("request_completed")
        assert client.proc.stdin
        client.proc.stdin.write("x" * 2_000_100 + "\n")
        client.proc.stdin.flush()
        assert client.wait("error")["code"] == "ProtocolError"
        client.send("open_status")
        assert client.wait("open_status")["active_revision"] == revision
        client.wait("request_completed")
    finally:
        client.close()
    restarted = NativeClient(tmp_path)
    try:
        assert restarted.ready["active_revision"] == revision
        assert all(event["run_id"] is None and event["call_id"] is None for event in restarted.observed)
    finally:
        restarted.close()


@pytest.mark.timeout(20)
def test_native_author_cancellation_rejects_overlapping_build(tmp_path: Path) -> None:
    client = NativeClient(tmp_path, [{"delay": 2, "text": json.dumps({"clarification": "Which answer?"})}])
    try:
        source = client.ready["snapshot"]["source_digest"]
        client.send("open_draft", source_digest=source, expected_revision=None)
        revision = client.wait("open_status")["source_revision"]
        client.wait("request_completed")
        client.send("open_resolve", source_digest=source, expected_revision=revision, goal="answer")
        activity = client.wait("open_activity")
        assert activity["domain"] == "author"
        client.send("open_build", source_digest=source, expected_revision=revision)
        assert "active" in client.wait("error")["message"]
        client.send("open_cancel", domain="author", activity_id=activity["activity_id"])
        client.wait("open_activity")
        client.wait("request_completed")
        completed = client.wait("open_activity")
        assert completed["activity"]["state"] == "cancelled"
        assert completed["activity_id"] == activity["activity_id"]
    finally:
        client.close()
