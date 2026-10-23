"""Drive the real built Ink UI and Python host in a credential-free POSIX PTY."""

from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")


def call(name: str, arguments: dict[str, Any], identifier: str) -> dict[str, Any]:
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}],
        }
    }


def main() -> None:
    output = ""
    evidence: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexa-ink-pty-") as directory:
        workspace = Path(directory)
        fixture = workspace / "fixture.json"
        fixture.write_text(
            json.dumps(
                [
                    call("Write", {"file_path": "verified.txt", "content": "offline verified\n"}, "pty-write"),
                    call("Read", {"file_path": "verified.txt", "offset": 0, "limit": 0, "pages": ""}, "pty-read"),
                    call("Bash", {"command": "test -s verified.txt && printf PTY-check-passed", "timeout": 5000, "run_in_background": False}, "pty-check"),
                    {"text": "PTY verified"},
                    {"delay": 10, "text": "should be cancelled"},
                ]
            )
        )
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 100, 0, 0))
        # Ink defers frames in CI; this child must render interactively on its real PTY.
        process = subprocess.Popen(
            ["node", str(ROOT / "ui-ink" / "dist" / "index.js"), "--cwd", directory, "--fixture", str(fixture)],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env={
                **os.environ,
                "CI": "false",
                "TERM": "xterm-256color",
                "FORCE_COLOR": "1",
                "UV_OFFLINE": "1",
                "UV_CACHE_DIR": "/tmp/nexa-code-uv-cache",
                "NEXA_QUIET": "1",
            },
        )
        os.close(slave)

        def read_until(text: str, since: int = 0) -> None:
            nonlocal output
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if text in ANSI.sub("", output[since:]):
                    return
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 65536).decode("utf-8", "replace")
                    except OSError:
                        break
                if process.poll() is not None:
                    break
            raise AssertionError(f"Missing PTY output: {text}\n{ANSI.sub('', output[-7000:])}")

        def send(value: str, expect: str) -> None:
            mark = len(output)
            if value.endswith("\r"):
                os.write(master, value[:-1].encode())
                read_until(value[:-1], mark)
                os.write(master, b"\r")
            else:
                os.write(master, value.encode())
            read_until(expect, mark)
            evidence.append(f"INPUT {value!r}\n" + ANSI.sub("", output[mark:])[-9000:])

        try:
            read_until("Ask Nexa")
            send("/version\r", "2.4.0.dev0")
            send("/theme light\r", "UI setting theme")
            send("write and verify α\r", "APPROVAL · Write")
            send("y", "APPROVAL · Bash")
            send("y", "PTY verified")
            assert (workspace / "verified.txt").read_text() == "offline verified\n"
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 60, 50, 0, 0))
            process.send_signal(signal.SIGWINCH)
            send("cancel this run\r", "model_started")
            send("\x1b", "cancelled")
            send("/resume\r", "Saved sessions")
            send("\x1b", "Ask Nexa")
            os.write(master, b"/exit")
            read_until("/exit", len(output))
            os.write(master, b"\r")
            deadline = time.monotonic() + 8
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 65536).decode("utf-8", "replace")
                    except OSError:
                        break
            assert process.wait(timeout=2) == 0
            evidence.append(
                "PASS: startup, commands, light theme, Unicode input, exact Write/Bash approvals, real file verification, 50-column resize, cancel, session picker, clean exit"
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            os.close(master)
            (ROOT / "docs" / "evidence" / "ink-pty.txt").write_text("\n\n".join(evidence), encoding="utf-8")
    print(evidence[-1])


if __name__ == "__main__":
    main()
