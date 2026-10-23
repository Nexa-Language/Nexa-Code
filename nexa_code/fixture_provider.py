"""Deterministic provider injection for credential-free integration tests."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.runtime.providers import ModelReply, ModelRequest


class FixtureProvider:
    name = "chat"

    def __init__(self, replies: list[ModelReply | dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.requests: list[ModelRequest] = []

    @classmethod
    def load(cls, path: Path) -> FixtureProvider:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("Fixture must be an array of provider replies")
        return cls(data)

    def complete(self, request: ModelRequest, on_text: Callable[[str], None] | None = None) -> ModelReply:
        self.requests.append(request)
        if not self.replies:
            raise ValueError("Fixture replies exhausted")
        item = self.replies.pop(0)
        if isinstance(item, ModelReply):
            return item
        delay = float(item.get("delay", 0))
        end = time.monotonic() + delay
        while time.monotonic() < end:
            time.sleep(min(0.01, max(0, end - time.monotonic())))
            if on_text:
                on_text("")
        message = item.get("message", {"role": "assistant", "content": item.get("text", "")})
        if message.get("content") and on_text:
            on_text(message["content"])
        return ModelReply(
            message, item.get("input_tokens", 10), item.get("output_tokens", 2), True, item.get("provider_items", []), item.get("provider_cursor", 0)
        )
