"""Exercise native Ink review, explicit grants and source-safe restart on a real PTY/OCI."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
from pathlib import Path

from pty_smoke import ANSI, ROOT
from src.open_programs.model import ApprovalState, PatchProposal
from src.open_programs.operations import PatchBinding
from src.open_programs.store import ProgramStore


class Terminal:
    def __init__(self, workspace: Path) -> None:
        self.output = ""
        self.evidence: list[str] = []
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 70, 140, 0, 0))
        self.process = subprocess.Popen(
            [
                "node",
                str(ROOT / "ui-ink/dist/index.js"),
                "--cwd",
                str(workspace),
                "--program",
                "maintain.nx",
                "--environment",
                "environment.json",
                "--state",
                "state.db",
                "--fixture",
                str(workspace / "replies.json"),
            ],
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

    def read_until(self, text: str | re.Pattern[str], since: int = 0) -> None:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            visible = ANSI.sub("", self.output[since:])
            matched = text.search(visible) if isinstance(text, re.Pattern) else text in visible
            if matched:
                return
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    self.output += os.read(self.master, 65536).decode("utf-8", "replace")
                except OSError:
                    break
            if self.process.poll() is not None:
                break
        raise AssertionError(f"Missing native PTY output: {text}\n{ANSI.sub('', self.output[-15000:])}")

    def send(self, command: str, expected: str) -> None:
        mark = len(self.output)
        os.write(self.master, command.encode())
        self.read_until(re.compile(r"›\s*" + re.escape(command[:30])), mark)
        submitted = len(self.output)
        os.write(self.master, b"\r")
        self.read_until(expected, submitted)
        if not command.startswith("/approve"):
            self.read_until("Ready for native command", submitted)
        self.evidence.append(f"COMMAND {command}\n" + ANSI.sub("", self.output[mark:])[-15000:])

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                os.write(self.master, b"/exit")
                self.read_until(re.compile(r"›\s*/exit"), len(self.output))
                os.write(self.master, b"\r")
                deadline = time.monotonic() + 5
                while self.process.poll() is None and time.monotonic() < deadline:
                    if select.select([self.master], [], [], 0.05)[0]:
                        try:
                            self.output += os.read(self.master, 65536).decode("utf-8", "replace")
                        except OSError:
                            break
                assert self.process.wait(timeout=3) == 0
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
            os.close(self.master)


def main() -> None:
    evidence: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nexa-open-pty-") as directory:
        workspace = Path(directory)
        fixtures = ROOT / "tests/fixtures/open-programs"
        for name in ("maintain.nx", "environment.json", "replies.json"):
            shutil.copyfile(fixtures / name, workspace / name)
        target = workspace / "calc.py"
        target.write_text("def add(a, b):\n    return a - b\n")
        terminal = Terminal(workspace)
        try:
            terminal.read_until("Ask Nexa")
            terminal.send("/build", "maintain · ready")
            terminal.send("/locked", "maintain · ready")
            terminal.send('/maintain {"paths":["calc.py"],"request":"Fix add"}', "checks.regression: passed")
            store = ProgramStore(workspace / "state.db")
            binding = store.references("patch.binding:", PatchBinding)[0]
            proposal = store.get(binding.proposal_digest, PatchProposal)
            assert "return a - b" in target.read_text()
            terminal.read_until(proposal.digest)
            terminal.send(f"/approve {proposal.digest} pty-user", "Confirm grant for the reviewed proposal")
            confirmed = len(terminal.output)
            os.write(terminal.master, b"y")
            terminal.read_until("grant issued; apply explicitly", confirmed)
            terminal.read_until("Ready for native command", confirmed)
            grant = store.references("approval:", ApprovalState)[0].grant
            assert "return a - b" in target.read_text()
            terminal.send(f"/apply {proposal.digest} {grant.digest}", "maintain · applied")
            assert target.read_text() == "def add(a, b):\n    return a + b\n"
            evidence.extend(terminal.evidence)
        finally:
            terminal.close()
        restarted = Terminal(workspace)
        try:
            restarted.read_until("Ask Nexa")
            restarted.read_until("Saved proposal: /proposal")
            restarted.read_until(proposal.digest)
            restarted.read_until(grant.digest)
            restarted.send("/status", "maintain · ready")
            evidence.extend(restarted.evidence)
        finally:
            restarted.close()
        evidence.append(
            "PASS: real Ink/host/OCI check/build/locked/maintenance; full diff and evidence; explicit grant confirmation; exact apply; unchanged host before grant/apply; restart restores proposal/grant; clean exit"
        )
    transcript = "\n".join(line.rstrip() for line in "\n\n".join(evidence).splitlines()) + "\n"
    (ROOT / "docs/evidence/ink-open-pty.txt").write_text(transcript, encoding="utf-8")
    print(evidence[-1])


if __name__ == "__main__":
    main()
