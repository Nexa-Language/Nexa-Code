"""Bounded asynchronous stdin host for the Nexa runtime."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .protocol import MAX_LINE, Emitter, ProtocolError, parse_request

if TYPE_CHECKING:
    from .session import Session


class Host:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.worker: threading.Thread | None = None
        self.busy = threading.Event()
        self.exiting = False
        self.closed = False
        self.clean = True

    def handle(self, request: dict[str, Any]) -> None:
        kind = request["type"]
        if kind.startswith("open_"):
            raise ProtocolError("Native requests require starting the engine with --program")
        if kind == "command" and request["name"].strip() in {"/exit", "/quit"}:
            kind = "exit"
        if kind == "exit":
            self.exiting = True
            if self.busy.is_set():
                self.session.request_cancel()
            return
        if kind == "cancel":
            self.session.cancel_pending() if not self.busy.is_set() else self.session.request_cancel()
            return
        if kind == "answer":
            if request["call_id"] != self.session.current_call_id:
                raise ValueError("Answer must match the active question call")
            with self.session.answer_lock:
                self.session.answers[request["call_id"]] = request["content"]
            return
        if self.busy.is_set():
            raise ValueError("A run is active; cancel it or wait for the result")
        self.session.cancel = threading.Event()
        if kind == "command":
            self.session.deadline = float("inf")
        self.busy.set()
        self.worker = threading.Thread(target=self._execute, args=(request,), daemon=True)
        self.worker.start()

    def _execute(self, request: dict[str, Any]) -> None:
        from .commands import run_command
        from .tool_services import active

        kind = request["type"]
        try:
            with active(self.session):
                if kind == "message":
                    self.session.message(request["content"], reset_cancel=False)
                elif kind == "approve":
                    self.session.approve(request["run_id"], request["call_id"], request["decision"], reset_cancel=False)
                elif kind == "resume":
                    self.session.resume(request["session_id"], reset_cancel=False)
                elif kind == "resolve":
                    self.session.resolve(request["run_id"], request["call_id"], request["content"], request["success"], reset_cancel=False)
                elif kind == "set_mode":
                    self.session.set_mode(request["mode"], confirmed=request.get("confirmed", False))
                elif kind == "command":
                    result = run_command(self.session, request["name"], reset_cancel=False)
                    if result == "__EXIT__":
                        self.exiting = True
                    else:
                        self.session.emit("command_result", name=request["name"], result=result)
        except Exception as error:  # noqa: BLE001 - User commands fail as explicit protocol errors.
            self.session.emit("error", code=type(error).__name__, message=str(error), request_id=request["request_id"])
        finally:
            self.busy.clear()
            self.session.emit("request_completed", request_id=request["request_id"])

    def close(self) -> bool:
        if self.closed:
            return self.clean
        self.closed = True
        self.clean = self.session.close()
        if self.worker:
            self.worker.join(timeout=3)
        self.clean = self.clean and (self.worker is None or not self.worker.is_alive())
        self.session.emit("session_end", clean=self.clean, reason="exit" if self.clean else "shutdown incomplete; inspect checkpoint and cleanup diagnostics")
        return self.clean


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexa Code checkpointed terminal engine")
    parser.add_argument("legacy_mode", nargs="?", choices=["default", "plan", "auto", "bypass"], help="Legacy positional permission mode")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--session")
    parser.add_argument("--model")
    parser.add_argument("--provider", choices=["chat", "responses", "anthropic"], default="chat")
    parser.add_argument("--mode", choices=["default", "plan", "auto", "bypass"])
    parser.add_argument("--fixture", type=Path, help="Explicit deterministic provider fixture; makes no model network requests")
    parser.add_argument("--legacy-protocol", action="store_true", help="Adapt unversioned 0.1 requests for one migration period")
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--program", type=Path, help="Explicit Nexa 3.0 Open Program source")
    parser.add_argument("--environment", type=Path, help="Native compiler environment JSON")
    parser.add_argument("--state", type=Path, default=Path(".nexa/open-programs.sqlite3"))
    parser.add_argument("--program-id")
    parser.add_argument("--docker-context")
    parser.add_argument("--max-model-calls", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=20000)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    fixture = args.fixture.resolve() if args.fixture else None
    os.environ["NEXA_QUIET"] = "1"
    os.environ.pop("NEXA_DEBUG", None)
    emitter = Emitter(sys.stdout)
    host: Host | None = None
    status = 0

    def interrupted(signum: int, frame: Any) -> None:
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        os.chdir(args.cwd.expanduser().resolve(strict=True))
        if args.program:
            from .open_host import run_native

            return run_native(args, emitter)
        from .commands import doctor
        from .fixture_provider import FixtureProvider
        from .session import Session

        if args.doctor:
            print(json.dumps(doctor(Path.cwd()), indent=2))
            return 0
        provider = FixtureProvider.load(fixture) if fixture else None
        session = Session(
            Path.cwd(),
            session_id=args.session,
            model=args.model,
            provider_api=args.provider,
            mode=args.mode or args.legacy_mode or "default",
            emitter=emitter,
            provider=provider,
        )
        host = Host(session)
        session.emit(
            "ready",
            model=session.agent.model,
            cwd=str(session.workspace),
            mode=session.policy.mode,
            capabilities=["checkpoint", "continue_run", "approval", "cancel", "artifacts", "legacy_import"],
            migration=session.policy.migration,
        )
        for name, value in session.settings.items():
            if name in {"theme", "editorMode"}:
                session.emit("ui_setting", name="vim" if name == "editorMode" else "theme", value=value)
        if session.state:
            session.emit("info", message="Saved checkpoint loaded. Use /resume " + session.id + " to continue pending work.")
        while not host.exiting:
            line = sys.stdin.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE and not line.endswith("\n"):
                while line and not line.endswith("\n"):
                    line = sys.stdin.readline(MAX_LINE + 1)
                session.emit("error", code="ProtocolError", message="Request exceeds 2 MB")
                continue
            try:
                host.handle(parse_request(line, legacy=args.legacy_protocol, legacy_run_id=session.state.run_id if session.state else None))
            except (ProtocolError, ValueError, TypeError) as error:
                session.emit("error", code=type(error).__name__, message=str(error))
    except BrokenPipeError:
        emitter.stream = None
        status = 1
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Startup failures have one protocol error boundary.
        emitter.emit("error", code=type(error).__name__, message=str(error) if not isinstance(error, KeyboardInterrupt) else "Interrupted")
        status = 130 if isinstance(error, KeyboardInterrupt) else 1
    finally:
        if host and not host.close() and status == 0:
            status = 2
        signal.signal(signal.SIGTERM, previous_term)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
