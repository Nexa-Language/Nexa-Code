"""Managed process groups with bounded capture and cancellation for every job."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from .session import Session

CAPTURE_LIMIT = 128_000


@dataclass
class Capture:
    chunks: list[str] = field(default_factory=list)
    received: int = 0

    def drain(self, stream: TextIO) -> None:
        try:
            while chunk := stream.read(8192):
                remaining = max(0, CAPTURE_LIMIT - self.received)
                if remaining:
                    self.chunks.append(chunk[:remaining])
                self.received += len(chunk)
        finally:
            stream.close()

    def text(self) -> str:
        extra = f"\n[output truncated: {self.received - CAPTURE_LIMIT} additional characters]" if self.received > CAPTURE_LIMIT else ""
        return "".join(self.chunks) + extra


@dataclass
class Job:
    process: subprocess.Popen[str]
    deadline: float
    cancel: threading.Event
    stdout: Capture = field(default_factory=Capture)
    stderr: Capture = field(default_factory=Capture)
    status: str = "running"
    done: threading.Event = field(default_factory=threading.Event)
    worker: threading.Thread | None = None
    error: Exception | None = None

    def run(self) -> None:
        assert self.process.stdout and self.process.stderr
        readers = [
            threading.Thread(target=capture.drain, args=(stream,), daemon=True)
            for capture, stream in ((self.stdout, self.process.stdout), (self.stderr, self.process.stderr))
        ]
        for reader in readers:
            reader.start()
        try:
            while self.process.poll() is None:
                if self.cancel.wait(0.02) or time.monotonic() >= self.deadline:
                    self.status = "cancelled" if self.cancel.is_set() else "timed_out"
                    terminate(self.process)
                    break
            if self.status == "running":
                self.status = "completed"
        except Exception as error:  # noqa: BLE001 - A job must publish completion even when process cleanup fails.
            self.error = error
            self.status = "cleanup_failed"
        finally:
            try:
                terminate(self.process)
                for reader in readers:
                    reader.join(timeout=0.1)
                if any(reader.is_alive() for reader in readers) and os.name == "posix":
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(self.process.pid, signal.SIGKILL)
                for reader in readers:
                    reader.join(timeout=1)
            except Exception as error:  # noqa: BLE001 - Propagate cleanup failure to the waiting tool instead of stranding it.
                self.error = error
                self.status = "cleanup_failed"
            finally:
                self.done.set()

    def result(self) -> dict[str, str | int | None]:
        return {"stdout": self.stdout.text(), "stderr": self.stderr.text(), "exit_code": self.process.returncode, "status": self.status}


def terminate(process: subprocess.Popen[str]) -> None:
    if os.name != "posix" and process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        elif process.poll() is None:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL) if os.name == "posix" else process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
    if os.name == "posix":
        # The process group may still own children after its shell leader exits.
        # Give them a bounded TERM grace period before enforcing group shutdown.
        time.sleep(0.1)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


def start(session: Session, argv: list[str], *, timeout: float, input_text: str | None = None) -> Job:
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as source:
        if input_text is not None:
            source.write(input_text)
            source.seek(0)
        process = subprocess.Popen(
            argv,
            cwd=session.workspace,
            stdin=source if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name == "posix",
        )
    job = Job(process, min(time.monotonic() + timeout, session.deadline), session.cancel)
    session.processes[str(process.pid)] = process
    session.jobs[str(process.pid)] = job
    job.worker = threading.Thread(target=job.run, daemon=True)
    job.worker.start()
    return job


def run(session: Session, argv: list[str], *, timeout: float = 120, input_text: str | None = None) -> dict[str, str | int | None]:
    job = start(session, argv, timeout=timeout, input_text=input_text)
    job.done.wait()
    session.processes.pop(str(job.process.pid), None)
    session.jobs.pop(str(job.process.pid), None)
    if job.error:
        from src.runtime.tool_dispatch import ToolOutcomeUnknown

        raise ToolOutcomeUnknown("Process cleanup failed: " + str(job.error)) from job.error
    return job.result()
