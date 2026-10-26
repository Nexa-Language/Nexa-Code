"""Strict native requests with identities independent of legacy tool approvals."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Nonempty = Annotated[str, Field(min_length=1)]


class NativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    request_id: Nonempty
    program_id: Nonempty


class QueryRequest(NativeRequest):
    type: Literal["open_check", "open_status", "open_resume"]


class SourceRequest(NativeRequest):
    type: Literal["open_build", "open_locked", "open_revise", "open_draft"]
    expected_revision: Nonempty | None
    source_digest: Nonempty


class GoalRequest(NativeRequest):
    type: Literal["open_run", "open_resolve"]
    expected_revision: Nonempty
    source_digest: Nonempty
    goal: Nonempty
    inputs: str = "{}"
    capsule_id: str = ""


class MaintainRequest(NativeRequest):
    type: Literal["open_maintain"]
    expected_revision: Nonempty
    source_digest: Nonempty
    paths: list[Nonempty] = Field(min_length=1)
    request: Nonempty
    event: Nonempty = "change_request"
    capsule_id: str = ""


class CancelRequest(NativeRequest):
    type: Literal["open_cancel"]
    domain: Literal["runtime", "author"]
    activity_id: Nonempty


class AnswerRequest(NativeRequest):
    type: Literal["open_answer"]
    expected_revision: Nonempty
    source_digest: Nonempty
    clarification_id: Nonempty
    answer: Nonempty


class SyncRequest(NativeRequest):
    type: Literal["open_sync"]
    sync_id: Nonempty
    confirmed: bool


class ProposalRequest(NativeRequest):
    type: Literal["open_proposal", "open_recover"]
    proposal_id: Nonempty


class GrantRequest(NativeRequest):
    type: Literal["open_grant"]
    proposal_id: Nonempty
    actor: Nonempty
    confirmed: bool
    expires_in: float = Field(default=3600, gt=0, le=3600)


class ApplyRequest(NativeRequest):
    type: Literal["open_apply"]
    proposal_id: Nonempty
    grant_id: Nonempty
    resume: bool = False


class ImportRequest(NativeRequest):
    type: Literal["open_import"]
    path: Nonempty


class ExportRequest(NativeRequest):
    type: Literal["open_export"]
    path: Nonempty
    activity_id: Nonempty
    source: Nonempty
    creator: Nonempty
    license: Nonempty


OpenRequest = Annotated[
    QueryRequest
    | SourceRequest
    | GoalRequest
    | MaintainRequest
    | CancelRequest
    | AnswerRequest
    | SyncRequest
    | ProposalRequest
    | GrantRequest
    | ApplyRequest
    | ImportRequest
    | ExportRequest,
    Field(discriminator="type"),
]
REQUEST_ADAPTER: TypeAdapter[OpenRequest] = TypeAdapter(OpenRequest)
