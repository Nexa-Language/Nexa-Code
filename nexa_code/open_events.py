"""Typed native event payloads validated before crossing the JSON Lines boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from src.open_programs.model import (
    AdmissionDecision,
    ApplyResult,
    ApprovalGrant,
    CheckReport,
    EffectIntent,
    EvidenceRecord,
    EvidenceStatus,
    ResolutionBudget,
    ResolutionResult,
    RuntimeActivity,
    RuntimeHead,
)
from src.open_programs.protocol import AuthorActivity

from .open_source import SourceSync


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PendingSource(SourceSync):
    sync_id: str


class SavedProposal(EventModel):
    proposal_id: str
    revision: str
    activity_id: str


class SavedGrant(EventModel):
    proposal_id: str
    grant_id: str
    expires_at: float
    revoked: bool


class SourceRecovery(EventModel):
    sync_id: str
    state: str
    original_path: str
    temporary_path: str


class ProgramSnapshot(EventModel):
    program_id: str
    source_revision: str | None
    active_revision: str | None
    head: RuntimeHead | None
    source_digest: str
    check: CheckReport
    budget: ResolutionBudget
    environment: str
    state_path: str
    runtime_activities: list[RuntimeActivity]
    author_activities: list[AuthorActivity]
    pending_sync: PendingSource | None
    source_recovery: list[SourceRecovery] = Field(default_factory=list)
    effects: list[EffectIntent]
    proposals: list[SavedProposal]
    grants: list[SavedGrant]


class Identity(EventModel):
    program_id: str
    source_revision: str | None
    active_revision: str | None
    request_id: str | None


class StatusEvent(Identity):
    type: Literal["open_ready", "open_status"]
    snapshot: ProgramSnapshot
    capabilities: list[str]


class ActivityEvent(Identity):
    type: Literal["open_activity"]
    domain: Literal["runtime", "author"]
    activity_id: str
    object_digest: str
    activity: RuntimeActivity | AuthorActivity


class ResultEvent(Identity):
    type: Literal["open_result"]
    domain: Literal["runtime"]
    activity_id: str
    result: ResolutionResult


class EvidenceView(EventModel):
    evidence_id: str
    record: EvidenceRecord
    validity: EvidenceStatus


class ProposalEvent(Identity):
    type: Literal["open_proposal"]
    proposal_id: str
    diff: str
    baseline_digest: str
    scope: list[str]
    task_id: str
    admission: AdmissionDecision
    evidence: list[EvidenceView]


class GrantEvent(Identity):
    type: Literal["open_grant"]
    proposal_id: str
    grant_id: str
    grant: ApprovalGrant


class ApplyEvent(Identity):
    type: Literal["open_applied"]
    proposal_id: str
    grant_id: str | None = None
    result: ApplyResult


class SyncEvent(Identity):
    type: Literal["open_source_sync"]
    sync_id: str
    sync: SourceSync


class CapsuleEvent(Identity):
    type: Literal["open_capsule"]
    capsule_id: str
    path: str
    action: Literal["import", "export"]


OPEN_EVENTS = TypeAdapter(
    Annotated[StatusEvent | ActivityEvent | ResultEvent | ProposalEvent | GrantEvent | ApplyEvent | SyncEvent | CapsuleEvent, Field(discriminator="type")]
)
