from __future__ import annotations

import pytest

from nexa_code.protocol import ProtocolError, parse_request


@pytest.mark.parametrize(
    "line", ["not json", "[]", "{}", '{"version":9,"type":"exit","request_id":"a"}', '{"version":1,"type":"message","request_id":"a","content":4}']
)
def test_invalid_protocol_is_explicit(line: str) -> None:
    with pytest.raises(ProtocolError):
        parse_request(line)


def test_v1_request_and_legacy_adapter() -> None:
    assert parse_request('{"version":1,"type":"message","request_id":"a","content":"hello"}')["content"] == "hello"
    request = parse_request('{"type":"message","content":"hello"}', legacy=True)
    assert request["version"] == 1
    assert request["request_id"]
    approval = parse_request('{"type":"permission_response","request_id":"call","approved":true}', legacy=True, legacy_run_id="run")
    assert approval["run_id"] == "run" and approval["call_id"] == "call" and approval["decision"] == "allow_once"
    with pytest.raises(ProtocolError):
        parse_request('{"type":"permission_response","approved":true}', legacy=True, legacy_run_id="run")
