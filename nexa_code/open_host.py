"""One managed native operation at a time, with exact-ID control while it runs."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

from src.open_programs.model import ProgramError, ResolutionBudget, RuntimeActivity
from src.open_programs.reuse import CapsuleOrigin

from .fixture_provider import FixtureProvider
from .open_events import OPEN_EVENTS
from .open_program import OpenConfig, OpenProgram
from .open_protocol import (
    REQUEST_ADAPTER,
    AnswerRequest,
    ApplyRequest,
    CancelRequest,
    ExportRequest,
    GoalRequest,
    GrantRequest,
    ImportRequest,
    MaintainRequest,
    OpenRequest,
    ProposalRequest,
    QueryRequest,
    SourceRequest,
    SyncRequest,
)
from .protocol import MAX_LINE, Emitter, ProtocolError, parse_request


class OpenHost:
    def __init__(self, program: OpenProgram, emitter: Emitter) -> None:
        self.program, self.emitter = program, emitter
        self.worker: threading.Thread | None = None
        self.busy = threading.Event()
        self.exiting = False
        self.request_id: str | None = None
        self.program.on_activity = self._created

    def emit(self, kind: str, *, request_id: str | None = None, **data: Any) -> None:
        revision = self.program.store.current_revision(self.program.config.program_id)
        try:
            head = self.program.session.runtime.status(self.program.config.program_id)
        except ProgramError as error:
            if error.code != "program_inactive":
                raise
            head = None
        event = OPEN_EVENTS.validate_python(
            {
                "type": kind,
                "request_id": request_id,
                "program_id": self.program.config.program_id,
                "source_revision": revision.digest if revision else None,
                "active_revision": head.revision if head else None,
                **data,
            }
        )
        payload = event.model_dump(mode="json", exclude={"type"})
        if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_LINE - 1024:
            raise ProgramError("event_limit", "Native result exceeds 2 MB; narrow the selected workspace/source scope")
        self.emitter.emit(kind, **payload)

    def _created(self, activity: RuntimeActivity) -> None:
        self.emit(
            "open_activity",
            request_id=self.request_id,
            domain="runtime",
            activity_id=activity.activity_id,
            object_digest=activity.digest,
            activity=activity.model_dump(mode="json"),
        )

    def status(self, *, ready: bool = False, request_id: str | None = None) -> None:
        snapshot = self.program.status()
        self.emit(
            "open_ready" if ready else "open_status",
            request_id=request_id,
            snapshot=snapshot,
            capabilities=["open_programs_3", "source_cas", "exact_activity_cancel", "exact_patch_grant", "capsule"],
        )

    def handle(self, payload: dict[str, Any]) -> None:
        if payload["type"] == "exit":
            self.exiting = True
            self.program.request_close()
            return
        if not payload["type"].startswith("open_"):
            raise ProtocolError("Open Programs require native requests; legacy modes and tool approvals do not apply")
        request = REQUEST_ADAPTER.validate_python(payload)
        if request.program_id != self.program.config.program_id:
            raise ProtocolError("Request program_id does not match this workspace")
        if isinstance(request, CancelRequest) or isinstance(request, QueryRequest) and request.type in {"open_status", "open_check"}:
            self._execute(request)
            return
        if self.busy.is_set():
            raise ProtocolError("A native operation is active; cancel its exact activity or wait for completion")
        self.busy.set()
        self.request_id = request.request_id
        self.worker = threading.Thread(target=self._execute, args=(request,), daemon=True, name="nexa-code-open")
        self.worker.start()

    def _execute(self, request: OpenRequest) -> None:
        control = isinstance(request, CancelRequest) or isinstance(request, QueryRequest) and request.type in {"open_status", "open_check"}
        try:
            self.dispatch(request)
        except Exception as error:  # noqa: BLE001 - Each operation returns a correlated, sanitized error.
            self.emitter.emit(
                "error",
                request_id=request.request_id,
                code=error.code if isinstance(error, ProgramError) else type(error).__name__,
                message=str(error) if isinstance(error, (ProgramError, OSError, ValueError)) else "Native operation failed; inspect its persisted activity",
            )
        finally:
            if not control:
                self.busy.clear()
            self.emitter.emit("request_completed", request_id=request.request_id)

    def dispatch(self, request: OpenRequest) -> None:
        program = self.program
        identifier = request.request_id
        if isinstance(request, QueryRequest):
            if request.type == "open_resume":
                program.resume()
            self.status(request_id=identifier)
        elif isinstance(request, SourceRequest):
            if request.type == "open_draft":
                program.propose_source(expected_revision=request.expected_revision, source_digest=request.source_digest)
            else:
                program.build(expected_revision=request.expected_revision, source_digest=request.source_digest, locked=request.type == "open_locked")
            self.status(request_id=identifier)
        elif isinstance(request, GoalRequest):
            self._goal(request)
        elif isinstance(request, MaintainRequest):
            activity, result, proposal = program.maintain(
                request.paths,
                request.request,
                expected_revision=request.expected_revision,
                source_digest=request.source_digest,
                event=request.event,
                capsule_digest=request.capsule_id,
            )
            self.emit("open_result", request_id=identifier, activity_id=activity, domain="runtime", result=result.model_dump(mode="json"))
            if proposal:
                self.emit("open_proposal", request_id=identifier, **program.inspect_proposal(proposal.digest))
            self.status(request_id=identifier)
        elif isinstance(request, CancelRequest):
            activity = program.cancel(request.activity_id, domain=request.domain)
            self.emit(
                "open_activity",
                request_id=identifier,
                domain=request.domain,
                activity_id=request.activity_id,
                object_digest=activity.digest,
                activity=activity.model_dump(mode="json"),
            )
        elif isinstance(request, (AnswerRequest, SyncRequest)):
            sync = (
                program.answer(request.clarification_id, request.answer, expected_revision=request.expected_revision, source_digest=request.source_digest)
                if isinstance(request, AnswerRequest)
                else program.sync_source(request.sync_id, confirmed=request.confirmed)
            )
            self.emit("open_source_sync", request_id=identifier, sync_id=sync.digest, sync=sync.model_dump(mode="json"))
            self.status(request_id=identifier)
        else:
            self._artifact(request)

    def _goal(self, request: GoalRequest) -> None:
        program = self.program
        if request.type == "open_run":
            activity, result = program.run_goal(
                request.goal,
                expected_revision=request.expected_revision,
                source_digest=request.source_digest,
                inputs=request.inputs,
                capsule_digest=request.capsule_id,
            )
            self.emit("open_result", request_id=request.request_id, activity_id=activity, domain="runtime", result=result.model_dump(mode="json"))
        else:
            activity = program.author_resolve(
                request.goal, expected_revision=request.expected_revision, source_digest=request.source_digest, inputs=request.inputs
            )
            previous = ""
            while True:
                value = program.author_activity(activity)
                if value.digest != previous:
                    self.emit(
                        "open_activity",
                        request_id=request.request_id,
                        domain="author",
                        activity_id=activity,
                        object_digest=value.digest,
                        activity=value.model_dump(mode="json"),
                    )
                    previous = value.digest
                if value.state != "running":
                    break
                time.sleep(0.05)
        self.status(request_id=request.request_id)

    def _artifact(self, request: ProposalRequest | GrantRequest | ApplyRequest | ImportRequest | ExportRequest) -> None:
        program, identifier = self.program, request.request_id
        if isinstance(request, ProposalRequest):
            if request.type == "open_proposal":
                self.emit("open_proposal", request_id=identifier, **program.inspect_proposal(request.proposal_id))
            else:
                self.emit(
                    "open_applied", request_id=identifier, proposal_id=request.proposal_id, result=program.recover(request.proposal_id).model_dump(mode="json")
                )
        elif isinstance(request, GrantRequest):
            grant = program.approve(request.proposal_id, actor=request.actor, confirmed=request.confirmed, expires_in=request.expires_in)
            self.emit("open_grant", request_id=identifier, proposal_id=request.proposal_id, grant_id=grant.digest, grant=grant.model_dump(mode="json"))
        elif isinstance(request, ApplyRequest):
            result = program.apply(request.proposal_id, request.grant_id, resume=request.resume)
            self.emit("open_applied", request_id=identifier, proposal_id=request.proposal_id, grant_id=request.grant_id, result=result.model_dump(mode="json"))
        elif isinstance(request, ImportRequest):
            capsule = program.import_capsule(Path(request.path))
            self.emit("open_capsule", request_id=identifier, capsule_id=capsule.digest, path=request.path, action="import")
        elif isinstance(request, ExportRequest):
            capsule = program.export_capsule(
                Path(request.path), request.activity_id, CapsuleOrigin(source=request.source, creator=request.creator, license=request.license)
            )
            self.emit("open_capsule", request_id=identifier, capsule_id=capsule.digest, path=request.path, action="export")

    def close(self) -> bool:
        self.program.request_close()
        if self.worker:
            self.worker.join(timeout=3)
        clean = self.worker is None or not self.worker.is_alive()
        if clean:
            self.program.close()
        self.emitter.emit("session_end", clean=clean, reason="exit" if clean else "Native worker remains active; inspect persisted activity before resume")
        return clean


def run_native(args: argparse.Namespace, emitter: Emitter) -> int:
    if not args.environment:
        raise ProgramError("environment_required", "Pass --environment <compiler-environment.json>; see docs/OPEN_PROGRAMS.md")
    if args.mode or args.legacy_mode or args.session or args.legacy_protocol or args.model or args.provider != "chat":
        raise ProgramError("native_mode_conflict", "Use --program with its compiler environment; omit legacy mode/session/protocol/model/provider flags")
    config = OpenConfig(
        source=args.program.resolve(),
        environment=args.environment.resolve(),
        state=args.state.resolve(),
        program_id=args.program_id or args.program.stem,
        workspace=Path.cwd(),
        docker_context=args.docker_context,
        budget=ResolutionBudget(max_model_calls=args.max_model_calls, max_tokens=args.max_tokens, timeout_seconds=args.timeout),
    )
    program = OpenProgram(config, provider=FixtureProvider.load(args.fixture) if args.fixture else None)
    host = OpenHost(program, emitter)
    try:
        host.status(ready=True)
        while not host.exiting:
            line = sys.stdin.readline(MAX_LINE + 1)
            if not line:
                break
            identifier: str | None = None
            try:
                if len(line) > MAX_LINE:
                    while line and not line.endswith("\n"):
                        line = sys.stdin.readline(MAX_LINE + 1)
                    raise ProtocolError("Request exceeds 2 MB")
                raw = json.loads(line)
                if isinstance(raw, dict) and isinstance(raw.get("request_id"), str):
                    identifier = raw["request_id"]
                host.handle(parse_request(line))
            except (ProtocolError, ValueError) as error:
                emitter.emit("error", request_id=identifier, code=type(error).__name__, message=str(error))
                if identifier:
                    emitter.emit("request_completed", request_id=identifier)
    finally:
        clean = host.close()
    return 0 if clean else 2
