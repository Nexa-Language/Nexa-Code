from __future__ import annotations

import json

import pytest

from nexa_code.protocol import ProtocolError, parse_request


def test_native_request_keeps_program_activity_and_grant_identities() -> None:
    request = parse_request(
        json.dumps({"version": 1, "type": "open_cancel", "request_id": "r", "program_id": "demo", "domain": "runtime", "activity_id": "selected"})
    )
    assert request["activity_id"] == "selected" and "call_id" not in request and "run_id" not in request
    grant = parse_request(
        json.dumps({"version": 1, "type": "open_apply", "request_id": "r", "program_id": "demo", "proposal_id": "proposal", "grant_id": "grant"})
    )
    assert grant["grant_id"] == "grant"


@pytest.mark.parametrize(
    "fields",
    [
        {"type": "open_cancel", "activity_id": "id"},
        {"type": "open_cancel", "activity_id": "id", "domain": "legacy"},
        {"type": "open_apply", "proposal_id": "id", "call_id": "legacy", "decision": "allow_session"},
        {"type": "open_grant", "proposal_id": "id", "actor": "user", "confirmed": "true"},
        {"type": "open_build", "source_digest": "digest"},
        {"type": "open_run", "goal": "g", "source_digest": "digest", "expected_revision": None},
    ],
)
def test_native_invalid_identity_is_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ProtocolError):
        parse_request(json.dumps({"version": 1, "request_id": "r", "program_id": "demo", **fields}))
