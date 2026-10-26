"""Versioned JSON Lines transport shared by terminal and headless clients."""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from typing import Any, TextIO

VERSION = 1
MAX_LINE = 2_000_000
REQUESTS = {"message", "command", "approve", "cancel", "exit", "set_mode", "resume", "resolve", "answer"}


class ProtocolError(ValueError):
    pass


def parse_request(line: str, *, legacy: bool = False, legacy_run_id: str | None = None) -> dict[str, Any]:
    if len(line.encode("utf-8")) > MAX_LINE:
        raise ProtocolError("Request exceeds 2 MB")
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, ValueError) as error:
        raise ProtocolError("Malformed JSON request") from error
    if not isinstance(value, dict):
        raise ProtocolError("Request must be an object")
    if legacy and "version" not in value:
        old_id = value.get("request_id")
        value = {"version": VERSION, "request_id": uuid.uuid4().hex, **value}
        if value.get("type") == "permission_response":
            value["type"], value["call_id"], value["run_id"] = "approve", old_id, legacy_run_id
            value["decision"] = "allow_once" if value.get("approved") is True or value.get("decision") in {"allow", "allow_once"} else "deny"
    if type(value.get("version")) is not int or value["version"] != VERSION:
        raise ProtocolError("Unsupported protocol version; expected 1")
    kind = value.get("type")
    if isinstance(kind, str) and kind.startswith("open_"):
        from pydantic import ValidationError

        from .open_protocol import REQUEST_ADAPTER

        try:
            return REQUEST_ADAPTER.validate_python(value).model_dump(mode="json")
        except ValidationError as error:
            raise ProtocolError("Invalid native request fields or identity") from error
    if value.get("type") not in REQUESTS or not isinstance(value.get("request_id"), str) or not value["request_id"]:
        raise ProtocolError("Known type and nonempty request_id are required")
    required = {
        "message": ["content"],
        "command": ["name"],
        "approve": ["run_id", "call_id", "decision"],
        "resume": ["session_id"],
        "set_mode": ["mode"],
        "resolve": ["run_id", "call_id", "content"],
        "answer": ["call_id", "content"],
    }
    for key in required.get(value["type"], []):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ProtocolError(f"{key} must be a nonempty string")
    if value["type"] == "approve" and value["decision"] not in {"allow_once", "deny", "allow_session", "allow_rule"}:
        raise ProtocolError("Invalid approval decision")
    if value["type"] == "resolve" and type(value.get("success")) is not bool:
        raise ProtocolError("Resolution requires explicit boolean success")
    if "confirmed" in value and type(value["confirmed"]) is not bool:
        raise ProtocolError("confirmed must be a boolean")
    return value


class Emitter:
    def __init__(self, stream: TextIO | None = None, callback: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.stream, self.callback = stream, callback
        self.sequence = 0
        self.lock = threading.Lock()
        self.session_id: str | None = None

    def emit(self, kind: str, *, run_id: str | None = None, call_id: str | None = None, **data: Any) -> None:
        with self.lock:
            self.sequence += 1
            event = {"version": VERSION, "sequence": self.sequence, "type": kind, "session_id": self.session_id, "run_id": run_id, "call_id": call_id, **data}
            if self.stream is not None:
                self.stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                self.stream.flush()
            if self.callback is not None:
                self.callback(event)
