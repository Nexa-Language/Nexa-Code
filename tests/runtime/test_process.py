from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, cwd: Path, replies: list[dict[str, Any]], session_id: str | None = None, *, legacy_mode: str | None = None) -> None:
        fixture = cwd / (uuid.uuid4().hex + ".fixture.json")
        fixture.write_text(json.dumps(replies))
        args = [sys.executable, "-m", "nexa_code.host", "--cwd", str(cwd), "--fixture", str(fixture)]
        if session_id:
            args += ["--session", session_id]
        if legacy_mode:
            args += [legacy_mode]
        self.proc = subprocess.Popen(
            args,
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.all: list[dict[str, Any]] = []
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.ready = self.wait("ready")

    def _read(self) -> None:
        assert self.proc.stdout
        for line in self.proc.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                self.events.put({"type": "invalid_output", "line": line})
                continue
            self.events.put(event)
            self.all.append(event)

    def send(self, kind: str, **payload: Any) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps({"version": 1, "type": kind, "request_id": uuid.uuid4().hex, **payload}) + "\n")
        self.proc.stdin.flush()

    def wait(self, kind: str) -> dict[str, Any]:
        while True:
            try:
                event = self.events.get(timeout=15)
            except queue.Empty as error:
                self.proc.kill()
                raise AssertionError(f"Missing event {kind}; observed {self.all}") from error
            if event["type"] == kind:
                return event
            assert event["type"] != "invalid_output", event
            if kind != "error":
                assert event["type"] != "error", event

    def close(self) -> None:
        if self.proc.poll() is None:
            self.send("exit")
            self.wait("session_end")
            assert self.proc.wait(timeout=5) == 0
        self.reader.join(timeout=1)
        assert self.proc.stdin and self.proc.stdout and self.proc.stderr
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.stderr.close()


def test_start_exit_two_turns_and_malformed_input(workspace: Path) -> None:
    client = Client(workspace, [{"text": "first"}, {"text": "second"}])
    try:
        assert client.ready["version"] == 1
        client.send("message", content="one")
        first = client.wait("done")
        client.wait("request_completed")
        client.send("message", content="two")
        second = client.wait("done")
        client.wait("request_completed")
        assert first["run_id"] != second["run_id"]
        assert second["reply"] == "second"
        assert client.proc.stdin
        client.proc.stdin.write("not json\n")
        client.proc.stdin.flush()
        assert client.wait("error")["code"] == "ProtocolError"
    finally:
        client.close()
    assert all(event["sequence"] == index + 1 for index, event in enumerate(client.all))


def test_legacy_positional_mode_for_both_engine_wrappers(workspace: Path) -> None:
    client = Client(workspace, [], legacy_mode="plan")
    try:
        assert client.ready["mode"] == "plan"
    finally:
        client.close()


def test_pending_approval_survives_actual_process_restart(workspace: Path) -> None:
    call = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "persist-call",
                    "type": "function",
                    "function": {"name": "Write", "arguments": json.dumps({"file_path": "saved.txt", "content": "persisted"})},
                }
            ],
        }
    }
    first = Client(workspace, [call])
    first.send("message", content="write")
    approval = first.wait("permission_request")
    first.wait("request_completed")
    # EOF preserves the waiting checkpoint. Explicit cancel/exit cancels an active approval.
    assert first.proc.stdin
    first.proc.stdin.close()
    assert first.proc.wait(timeout=5) == 0
    second = Client(workspace, [{"text": "done"}], first.ready["session_id"])
    try:
        second.send("approve", run_id=approval["run_id"], call_id=approval["call_id"], decision="allow_once")
        result = second.wait("done")
        assert result["status"] == "completed"
        assert (workspace / "saved.txt").read_text() == "persisted"
    finally:
        second.close()


def test_cancel_during_provider_stream(workspace: Path) -> None:
    client = Client(workspace, [{"delay": 5, "text": "late"}])
    try:
        client.send("message", content="slow")
        client.wait("runtime_event")
        client.send("cancel")
        result = client.wait("done")
        assert result["status"] == "cancelled"
    finally:
        client.close()


def test_signal_cleanup_stops_independent_child_group(workspace: Path) -> None:
    call = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "shell",
                    "type": "function",
                    "function": {
                        "name": "Bash",
                        "arguments": json.dumps({"command": "echo $$ > child.pid; sleep 20", "timeout": 30000, "run_in_background": False}),
                    },
                }
            ],
        }
    }
    client = Client(workspace, [call, {"text": "late"}])
    client.send("message", content="check")
    approval = client.wait("permission_request")
    client.wait("request_completed")
    client.send("approve", run_id=approval["run_id"], call_id="shell", decision="allow_once")
    path = workspace / "child.pid"
    end = time.monotonic() + 3
    while not path.exists() and time.monotonic() < end:
        time.sleep(0.01)
    assert path.exists()
    child_pid = int(path.read_text())
    client.proc.send_signal(signal.SIGINT)
    assert client.proc.wait(timeout=5) == 130
    client.reader.join(timeout=1)
    assert len([event for event in client.all if event["type"] == "session_end"]) == 1
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        pass
    else:
        os.killpg(child_pid, signal.SIGKILL)
        raise AssertionError("Shell process survived host interrupt")
    client.close()
