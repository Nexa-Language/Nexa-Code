"""Native Open Programs orchestration; policy, execution and journals stay in Nexa."""

from __future__ import annotations

import tempfile
import threading
import time
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from src.open_programs.compiler import CandidateExecutor, OpenCompiler
from src.open_programs.controller import RuntimeController
from src.open_programs.environment import load_environment, model_provider
from src.open_programs.evidence import current_evidence, evaluate_policy, validate_evidence
from src.open_programs.executor import OCIExecutor
from src.open_programs.frontend import check
from src.open_programs.model import (
    ApplyResult,
    ApprovalGrant,
    ApprovalState,
    CheckReport,
    PatchProposal,
    ProgramError,
    ProgramRevision,
    ResolutionBudget,
    ResolutionResult,
    RuntimeActivity,
    RuntimeHead,
    SourceBundle,
)
from src.open_programs.operations import PatchBinding, ProgramSession
from src.open_programs.protocol import AnswerParams, AuthorActivity, AuthorProtocol
from src.open_programs.reuse import CapsuleOrigin, ImplementationCapsule, export_capsule, read_capsule, write_capsule
from src.open_programs.store import ProgramStore
from src.runtime.providers import ModelProvider

from .open_source import SourceSync, SourceSynchronizer, checked
from .source_write import read_source


@dataclass(frozen=True)
class OpenConfig:
    source: Path
    environment: Path
    state: Path
    program_id: str
    workspace: Path
    budget: ResolutionBudget = field(default_factory=ResolutionBudget)
    docker_context: str | None = None


class ObservedRuntime(RuntimeController):
    def __init__(self, compiler: OpenCompiler, created: Callable[[RuntimeActivity], None]) -> None:
        super().__init__(compiler)
        self.created = created

    def start_activity(self, program_id: str, goal_name: str, *, input_json: str = "{}", capsule_digest: str = "") -> RuntimeActivity:
        activity = super().start_activity(program_id, goal_name, input_json=input_json, capsule_digest=capsule_digest)
        self.created(activity)
        return activity


class OpenProgram:
    def __init__(
        self,
        config: OpenConfig,
        *,
        provider: ModelProvider | None = None,
        executor: CandidateExecutor | None = None,
        on_activity: Callable[[RuntimeActivity], None] | None = None,
    ) -> None:
        self.config = config
        self.store = ProgramStore(config.state)
        self.compiler = OpenCompiler(
            load_environment(config.environment), self.store, executor=executor or OCIExecutor(context=config.docker_context), provider=provider
        )
        self.resources = ExitStack()
        self.provider_ready = provider is not None
        self.owned_runtime: set[str] = set()
        self.owned_author: set[str] = set()
        self.closing = threading.Event()
        self.on_activity = on_activity
        self.selection: tuple[str, str] | None = None
        self.session = ProgramSession(self.compiler)
        self.session.runtime = ObservedRuntime(self.compiler, self._activity_created)
        self.author = AuthorProtocol(self.store, self.compiler)
        self.source_sync = SourceSynchronizer(self.store, self.author, config.program_id, config.source)

    def _activity_created(self, activity: RuntimeActivity) -> None:
        self.owned_runtime.add(activity.activity_id)
        if self.selection:
            revision, digest = self.selection
            try:
                self._environment_current()
                self._source(revision, digest)
                if activity.revision != revision:
                    raise ProgramError("revision_conflict", "Activity was created on a different active revision")
            except ProgramError:
                self.session.runtime.cancel(activity.activity_id)
                raise
        if self.closing.is_set():
            self.session.runtime.cancel(activity.activity_id)
        if self.on_activity:
            self.on_activity(activity)

    def _provider(self, *, locked: bool = False) -> None:
        self._environment_current()
        if locked or self.provider_ready:
            return
        self.compiler.provider = self.resources.enter_context(model_provider(self.compiler.environment))
        self.provider_ready = True

    def _environment_current(self) -> None:
        try:
            current = load_environment(self.config.environment)
        except (OSError, ValueError, ProgramError) as error:
            raise ProgramError("environment_unavailable", "Cannot validate the compiler environment; repair the file and restart the native client") from error
        if current.digest != self.compiler.environment.digest:
            raise ProgramError(
                "environment_changed", "Compiler environment changed; restart the native client, rebuild and review new evidence before execution"
            )

    def check(self) -> CheckReport:
        self.source_sync.recover()
        return check(SourceBundle(text=read_source(self.config.source), path=str(self.config.source)))

    def _source(self, expected_revision: str | None, source_digest: str) -> CheckReport:
        self.source_sync.ensure_ready()
        current = self.store.current_revision(self.config.program_id)
        if (current.digest if current else None) != expected_revision:
            raise ProgramError("revision_conflict", "Refresh source and active revisions before retrying")
        report = checked(read_source(self.config.source), self.config.source)
        if report.source_digest != source_digest:
            raise ProgramError("source_conflict", "Source changed since the displayed check")
        return report

    def build(self, *, expected_revision: str | None, source_digest: str, locked: bool = False) -> RuntimeHead:
        self._source(expected_revision, source_digest)
        text = self._source_text(source_digest)
        self._provider(locked=locked)
        # activate() rereads its path. Bind that read to the exact checked bytes, even during editor saves.
        with tempfile.TemporaryDirectory(prefix="nexa-code-source-") as directory:
            snapshot = Path(directory) / self.config.source.name
            snapshot.write_text(text, encoding="utf-8")
            head = self.session.activate(
                snapshot,
                program_id=self.config.program_id,
                expected_revision=expected_revision,
                locked=locked,
                lock_path=self.config.source.with_suffix(".nx.lock"),
                budget=self.config.budget,
            )
        self._source_text(source_digest)
        return head

    def _source_text(self, digest: str) -> str:
        text = read_source(self.config.source)
        if checked(text, self.config.source).source_digest != digest:
            raise ProgramError("source_conflict", "Source changed since the checked snapshot; refresh before continuing")
        return text

    def propose_source(self, *, expected_revision: str | None, source_digest: str) -> str:
        report = self._source(expected_revision, source_digest)
        response = self._author(
            "revision/propose",
            {
                "program_id": self.config.program_id,
                "expected_revision": expected_revision,
                "source": self._source_text(source_digest),
                "path": str(self.config.source),
            },
        )
        if "revision" not in response or report.program is None:
            raise ProgramError("source_invalid", "Draft failed native validation")
        return str(response["revision"])

    def _active(self, expected_revision: str, source_digest: str) -> None:
        report = self._source(expected_revision, source_digest)
        head = self.session.runtime.status(self.config.program_id)
        revision = self.store.get(head.revision, ProgramRevision)
        if head.revision != expected_revision or report.program is None or report.program.digest != revision.program.digest:
            raise ProgramError("revision_inactive", "Build the checked source revision before executing it")
        self._provider()

    def run_goal(
        self, goal: str, *, expected_revision: str, source_digest: str, inputs: str = "{}", budget: ResolutionBudget | None = None, capsule_digest: str = ""
    ) -> tuple[str, ResolutionResult]:
        with self._selected(expected_revision, source_digest):
            return self.session.run_goal(self.config.program_id, goal, inputs=inputs, budget=budget or self.config.budget, capsule_digest=capsule_digest)

    def maintain(
        self, paths: list[str], request: str, *, expected_revision: str, source_digest: str, event: str = "change_request", capsule_digest: str = ""
    ) -> tuple[str, ResolutionResult, PatchProposal | None]:
        with self._selected(expected_revision, source_digest):
            return self.session.maintain(
                self.config.program_id, self.config.workspace, paths, request, event=event, budget=self.config.budget, capsule_digest=capsule_digest
            )

    @contextmanager
    def _selected(self, revision: str, source_digest: str) -> Generator[None, None, None]:
        self._active(revision, source_digest)
        self.selection = revision, source_digest
        try:
            yield
        finally:
            self.selection = None

    def runtime_activities(self) -> list[RuntimeActivity]:
        identifiers: set[str] = set()
        for _, event in self.store.events(self.config.program_id):
            if event.kind in {"activity_created", "activity_completed", "activity_blocked", "activity_cancelled"}:
                identifiers.add(self.store.get(event.object_id, RuntimeActivity).activity_id)
        return [self.session.runtime.activity(identifier) for identifier in sorted(identifiers)]

    def author_activities(self) -> list[AuthorActivity]:
        return [activity for activity in self.store.references("activity:", AuthorActivity) if activity.program_id == self.config.program_id]

    def author_activity(self, identifier: str) -> AuthorActivity:
        activity = self.store.reference("activity:" + identifier, AuthorActivity)
        if activity is None:
            raise ProgramError("activity_missing", identifier)
        self._identity(activity.program_id)
        return activity

    def _identity(self, program_id: str) -> None:
        if program_id != self.config.program_id:
            raise ProgramError("program_mismatch", "Object belongs to another program")

    def cancel(self, activity_id: str, *, domain: Literal["runtime", "author"]) -> RuntimeActivity | AuthorActivity:
        if domain == "author":
            self.author_activity(activity_id)
            self._author("activity/cancel", {"object_id": activity_id})
            return self.author_activity(activity_id)
        activity = self.session.runtime.activity(activity_id)
        self._identity(activity.program_id)
        return self.session.runtime.cancel(activity_id)

    def status(self) -> dict[str, Any]:
        revision = self.store.current_revision(self.config.program_id)
        try:
            head = self.session.runtime.status(self.config.program_id)
        except ProgramError as error:
            if error.code != "program_inactive":
                raise
            head = None
        pending = self.source_sync.pending()
        report = self.check()
        return {
            "program_id": self.config.program_id,
            "source_revision": revision.digest if revision else None,
            "active_revision": head.revision if head else None,
            "head": head.model_dump(mode="json") if head else None,
            "source_digest": report.source_digest,
            "check": report.model_dump(mode="json"),
            "budget": self.config.budget.model_dump(mode="json"),
            "environment": str(self.config.environment),
            "state_path": str(self.config.state),
            "runtime_activities": [activity.model_dump(mode="json") for activity in self.runtime_activities()],
            "author_activities": [activity.model_dump(mode="json") for activity in self.author_activities()],
            "pending_sync": {"sync_id": pending.digest, **pending.model_dump(mode="json")} if pending else None,
            "source_recovery": self.source_sync.writer.views(),
            "effects": [effect.model_dump(mode="json") for effect in self.session.runtime.effects.pending(self.config.program_id)],
            **self.saved_proposals(),
        }

    def saved_proposals(self) -> dict[str, Any]:
        proposals = []
        for binding in self.store.references("patch.binding:", PatchBinding):
            if binding.program_id != self.config.program_id:
                continue
            proposal = self.store.get(binding.proposal_digest, PatchProposal)
            if Path(proposal.baseline.root).resolve() == self.config.workspace.resolve():
                proposals.append({"proposal_id": proposal.digest, "revision": binding.revision, "activity_id": binding.activity_id})
        identifiers = {item["proposal_id"] for item in proposals}
        grants = [
            {"proposal_id": item.grant.proposal_digest, "grant_id": item.grant.digest, "expires_at": item.grant.expires_at, "revoked": item.revoked}
            for item in self.store.references("approval:", ApprovalState)
            if item.grant.proposal_digest in identifiers
        ]
        return {"proposals": proposals, "grants": grants}

    def _author(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.author.handle({"jsonrpc": "2.0", "id": "code", "method": method, "params": params})
        if response is None:
            raise ProgramError("author_response_missing", method)
        if "error" in response:
            error = cast(dict[str, Any], response["error"])
            raise ProgramError(error.get("data", {}).get("code") or "author_error", error["message"])
        return cast(dict[str, Any], response["result"])

    def author_resolve(self, goal: str, *, expected_revision: str, source_digest: str, inputs: str = "{}") -> str:
        report = self._source(expected_revision, source_digest)
        revision = self.store.get(expected_revision, ProgramRevision)
        if report.program is None or report.program.digest != revision.program.digest:
            raise ProgramError("source_draft_mismatch", "Checked source differs from the selected draft; use /draft or /build before /resolve")
        self._provider()
        result = self._author(
            "goal/resolve",
            {
                "program_id": self.config.program_id,
                "expected_revision": expected_revision,
                "goal": goal,
                "input_json": inputs,
                "budget": self.config.budget.model_dump(mode="json"),
            },
        )
        identifier = str(result["activity_id"])
        self.owned_author.add(identifier)
        return identifier

    def answer(self, clarification_id: str, answer: str, *, expected_revision: str, source_digest: str) -> SourceSync:
        return self.source_sync.prepare(
            AnswerParams(program_id=self.config.program_id, expected_revision=expected_revision, request_id=clarification_id, answer=answer), source_digest
        )

    def sync_source(self, sync_id: str, *, confirmed: bool) -> SourceSync:
        return self.source_sync.synchronize(sync_id, confirmed=confirmed)

    def proposal(self, proposal_id: str) -> PatchProposal:
        proposal = self.store.get(proposal_id, PatchProposal)
        binding = self.store.reference("patch.binding:" + proposal.digest, PatchBinding)
        if binding is None:
            raise ProgramError("patch_binding_missing", proposal_id)
        self._identity(binding.program_id)
        if Path(proposal.baseline.root).resolve() != self.config.workspace.resolve():
            raise ProgramError("workspace_mismatch", "Proposal belongs to another workspace")
        return proposal

    def inspect_proposal(self, proposal_id: str) -> dict[str, Any]:
        self._environment_current()
        proposal = self.proposal(proposal_id)
        policy, context = self.session.current_patch_context(proposal)
        records = current_evidence(self.store, list(proposal.evidence), context)
        return {
            "proposal_id": proposal.digest,
            "diff": proposal.diff,
            "baseline_digest": proposal.baseline.digest,
            "scope": [change.path for change in proposal.changes],
            "task_id": proposal.task_id,
            "admission": evaluate_policy(policy, records, context).model_dump(mode="json"),
            "evidence": [
                {"evidence_id": record.digest, "record": record.model_dump(mode="json"), "validity": validate_evidence(record, context).model_dump(mode="json")}
                for record in records
            ],
        }

    def approve(self, proposal_id: str, *, actor: str, confirmed: bool, expires_in: float = 3600) -> ApprovalGrant:
        if not confirmed:
            raise ProgramError("confirmation_required", "Review the exact proposal diff and evidence before granting permission")
        if not actor.strip() or not 0 < expires_in <= 3600:
            raise ProgramError("approval_invalid", "An identified actor and expiry of up to 3600 seconds are required")
        self.source_sync.ensure_ready()
        if not self.inspect_proposal(proposal_id)["admission"]["accepted"]:
            raise ProgramError("evidence_stale", "Current native evidence no longer admits this proposal")
        return self.session.workspace.approve(self.proposal(proposal_id), actor=actor, expires_at=time.time() + expires_in)

    def apply(self, proposal_id: str, grant_id: str, *, resume: bool = False) -> ApplyResult:
        self._environment_current()
        self.source_sync.ensure_ready()
        proposal = self.proposal(proposal_id)
        approval = self.store.reference("approval:" + grant_id, ApprovalState)
        if approval is None:
            raise ProgramError("approval_invalid", "Unknown native grant")
        return self.session.apply(proposal, approval.grant, resume=resume)

    def recover(self, proposal_id: str) -> ApplyResult:
        return self.session.workspace.recover(self.proposal(proposal_id))

    def resume(self) -> RuntimeHead:
        self._environment_current()
        return self.session.runtime.resume(self.config.program_id)

    def import_capsule(self, path: Path) -> ImplementationCapsule:
        capsule = read_capsule(path)
        self.store.put(capsule)
        return capsule

    def export_capsule(self, path: Path, activity_id: str, origin: CapsuleOrigin) -> ImplementationCapsule:
        activity = self.session.runtime.activity(activity_id)
        self._identity(activity.program_id)
        if activity.result is None:
            raise ProgramError("activity_incomplete", activity_id)
        revision = self.store.get(activity.revision, ProgramRevision)
        goal = next(goal for goal in revision.program.goals if goal.name == activity.goal)
        capsule = export_capsule(goal, activity.result, origin)
        write_capsule(capsule, path)
        self.store.put(capsule)
        return capsule

    def request_close(self) -> None:
        self.closing.set()
        for identifier in tuple(self.owned_runtime):
            self.cancel(identifier, domain="runtime")
        for identifier in tuple(self.owned_author):
            self.cancel(identifier, domain="author")

    def close(self) -> None:
        self.request_close()
        self.author.close()
        self.resources.close()
