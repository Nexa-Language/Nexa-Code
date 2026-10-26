"""Durable, reviewable synchronization of author intent with its source file."""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Literal

from src.open_programs.frontend import check
from src.open_programs.model import CheckReport, FrozenModel, ProgramError, ProgramEvent, ProgramIR, ProgramRevision, SourceBundle, content_digest
from src.open_programs.protocol import AnswerParams, AuthorProtocol
from src.open_programs.store import ProgramStore

from .source_write import SourceWriter, read_source


def checked(text: str, path: Path) -> CheckReport:
    report = check(SourceBundle(text=text, path=str(path)))
    if not report.ok or report.program is None:
        raise ProgramError("source_invalid", "; ".join(f"{item.code}@{item.span.line}:{item.span.column}: {item.message}" for item in report.diagnostics))
    return report


def intent_source(text: str, path: Path, before: ProgramIR, after: ProgramIR) -> str:
    """Locate strings only inside native goal spans; the frontend verifies the full result."""
    edits: list[tuple[int, int, str]] = []
    lines = text.splitlines(keepends=True)
    goals = {goal.name: goal for goal in after.goals}
    for goal in before.goals:
        target = goals.get(goal.name)
        if target is None or target.intent == goal.intent:
            continue
        start = sum(map(len, lines[: goal.span.line - 1])) + goal.span.column - 1
        end = sum(map(len, lines[: goal.span.end_line - 1])) + goal.span.end_column - 1
        tokens = [token for token in re.finditer(r'//[^\n]*|"(?:[^"\\]|\\.)*"|[A-Za-z_]\w*|[^\s]', text[start:end]) if not token.group().startswith("//")]
        matches = [tokens[index + 1] for index, token in enumerate(tokens[:-1]) if token.group() == "intent" and tokens[index + 1].group().startswith('"')]
        if len(matches) != 1 or json.loads(matches[0].group()) != goal.intent:
            raise ProgramError("source_span_conflict", goal.name)
        token = matches[0]
        edits.append((start + token.start(), start + token.end(), json.dumps(target.intent, ensure_ascii=False)))
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    report = checked(text, path)
    if report.program is None or report.program.digest != after.digest:
        raise ProgramError("source_ir_mismatch", "Synchronization must change only the intended goal intent")
    return text


class SourceSync(FrozenModel):
    program_id: str
    path: str
    base_revision: str
    revision: str
    base_source: str
    base_digest: str
    source: str
    source_digest: str
    clarification_id: str
    answer: str
    diff: str
    state: Literal["prepared", "pending", "rejected", "applied"] = "prepared"


class SourceSynchronizer:
    def __init__(self, store: ProgramStore, author: AuthorProtocol, program_id: str, path: Path) -> None:
        self.store, self.author, self.program_id, self.path = store, author, program_id, path
        self.key = "code.source-sync:" + content_digest((program_id, str(path)))
        self.writer = SourceWriter(store, path, self.key)

    def recover(self) -> None:
        if not self.writer.records():
            return
        with self.store.lease(self.key):
            self.writer.recover()

    def pending(self) -> SourceSync | None:
        record = self.store.reference(self.key, SourceSync)
        return record if record and record.state != "applied" else None

    def ensure_ready(self) -> None:
        if self.pending():
            raise ProgramError("source_sync_pending", "Review and confirm the pending intent diff before building or running")
        current = self.store.current_revision(self.program_id)
        if current and any(event.kind == "author_answered" and event.object_id == current.digest for _, event in self.store.events(self.program_id)):
            report = checked(read_source(self.path), self.path)
            if report.program is None or report.program.digest != current.program.digest:
                raise ProgramError("source_sync_pending", "The stored author clarification must be synchronized to this source before execution")

    def prepare(self, params: AnswerParams, source_digest: str) -> SourceSync:
        with self.store.lease(self.key):
            self.ensure_ready()
            text = read_source(self.path)
            report = checked(text, self.path)
            previous = self.store.current_revision(self.program_id)
            if previous is None or previous.digest != params.expected_revision:
                raise ProgramError("revision_conflict", self.program_id)
            if report.source_digest != source_digest or report.program is None or report.program.digest != previous.program.digest:
                raise ProgramError("source_conflict", "Source changed since the author activity")
            from src.open_programs.protocol import AuthorActivity

            activity = self.store.reference("clarification:" + params.request_id, AuthorActivity)
            if activity is None or activity.program_id != self.program_id or activity.revision != previous.digest:
                raise ProgramError("clarification_missing", params.request_id)
            goals = tuple(
                goal.model_copy(update={"intent": goal.intent + "\nAuthor clarification: " + params.answer}) if goal.name == activity.goal else goal
                for goal in previous.program.goals
            )
            updated = ProgramRevision(program_id=self.program_id, parent=previous.digest, program=previous.program.model_copy(update={"goals": goals}))
            source = intent_source(text, self.path, report.program, updated.program)
            pending = SourceSync(
                program_id=self.program_id,
                path=str(self.path),
                base_revision=previous.digest,
                revision=updated.digest,
                base_source=text,
                base_digest=source_digest,
                source=source,
                source_digest=checked(source, self.path).source_digest,
                clarification_id=params.request_id,
                answer=params.answer,
                diff="".join(
                    difflib.unified_diff(text.splitlines(keepends=True), source.splitlines(keepends=True), fromfile=str(self.path), tofile=str(self.path))
                ),
            )
            old = self.store.reference(self.key, SourceSync)
            self.store.set_reference(self.key, old.digest if old else None, pending)
            return self._answer(pending)

    def _answer(self, pending: SourceSync) -> SourceSync:
        current = self.store.current_revision(self.program_id)
        if current and current.digest == pending.base_revision:
            response = self.author.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "source-sync",
                    "method": "author/answer",
                    "params": {
                        "program_id": self.program_id,
                        "expected_revision": pending.base_revision,
                        "request_id": pending.clarification_id,
                        "answer": pending.answer,
                    },
                }
            )
            if response is None or "error" in response:
                raise ProgramError("source_sync_pending", "Author answer was not committed; review the stored clarification before retrying")
            current = self.store.current_revision(self.program_id)
        if current is None or current.digest != pending.revision:
            raise ProgramError("revision_conflict", "The pending intent belongs to a different draft revision")
        updated = pending.model_copy(update={"state": "pending"})
        self.store.set_reference(self.key, pending.digest, updated)
        return updated

    def synchronize(self, sync_id: str, *, confirmed: bool) -> SourceSync:
        with self.store.lease(self.key):
            self.writer.recover()
            pending = self.pending()
            if pending is None or pending.digest != sync_id:
                raise ProgramError("source_sync_conflict", "Select the exact pending intent diff")
            if not confirmed:
                rejected = pending.model_copy(update={"state": "rejected"})
                self.store.set_reference(self.key, pending.digest, rejected)
                return rejected
            if pending.state == "prepared":
                pending = self._answer(pending)
            current = self.store.current_revision(self.program_id)
            if current and current.parent == pending.revision and read_source(self.path) == pending.source:
                expected = checked(pending.source, self.path)
                if (
                    expected.program
                    and current.program.digest == expected.program.digest
                    and any(event.kind == "source_synchronized" and event.object_id == current.digest for _, event in self.store.events(self.program_id))
                ):
                    return self._applied(pending, current.digest)
            if current is None or current.digest != pending.revision:
                raise ProgramError("revision_conflict", self.program_id)
            report = checked(pending.source, self.path)
            if report.program is None or report.program.digest != current.program.digest:
                raise ProgramError("source_ir_mismatch", "Stored source no longer represents the clarified intent")
            self._write(pending)
            revision = ProgramRevision(program_id=self.program_id, parent=current.digest, program=report.program)
            # Source may already be written after a process interruption; revision CAS is still required.
            self.store.commit_revision(current.digest, revision, [ProgramEvent(kind="source_synchronized", object_id=revision.digest)])
            return self._applied(pending, revision.digest)

    def _applied(self, pending: SourceSync, revision: str) -> SourceSync:
        applied = pending.model_copy(update={"state": "applied", "revision": revision})
        self.writer.complete(pending.base_digest, pending.source_digest)
        self.store.set_reference(self.key, pending.digest, applied)
        return applied

    def _write(self, pending: SourceSync) -> None:
        self.writer.write(pending.digest, pending.base_source, pending.source)
