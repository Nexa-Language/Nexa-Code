"""Session catalog adjacent to the runtime's transactional checkpoints."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from src.runtime.checkpoints import SQLiteCheckpointStore
from src.runtime.run_state import RunState


class Sessions:
    def __init__(self, path: Path) -> None:
        self.checkpoints = SQLiteCheckpointStore(path)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS code_sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def create(self, workspace: Path, model: str, provider: str, definition: str, **extra: Any) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "workspace": str(workspace),
            "model": model,
            "provider": provider,
            "definition": definition,
            "created_at": time.time(),
            "title": "New session",
            **extra,
        }
        self.put(record)
        return record

    def put(self, record: dict[str, Any]) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO code_sessions VALUES (?, ?)", (record["id"], json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def get(self, session_id: str) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT data FROM code_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("Session not found")
        return json.loads(row[0])

    def list_sessions(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT data FROM code_sessions ORDER BY rowid DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def runs(self, session_id: str, *, include_children: bool = False) -> list[RunState]:
        with sqlite3.connect(self.path) as db:
            condition = "json_extract(state, '$.metadata.session_id')=?"
            params = (session_id,)
            if include_children:
                condition += " OR json_extract(state, '$.metadata.parent_session_id')=?"
                params = (session_id, session_id)
            rows = db.execute("SELECT state FROM runs WHERE " + condition + " ORDER BY rowid", params).fetchall()
        return [RunState.from_dict(json.loads(row[0])) for row in rows]


def read_legacy(path: Path) -> str:
    if path.stat().st_size > 10_000_000:
        raise ValueError("Legacy transcript exceeds 10 MB; inspect it read-only before selecting a smaller export")
    lines: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            messages = item.get("messages", [item]) if isinstance(item, dict) else []
            if not isinstance(messages, list) or not messages:
                raise ValueError("Expected message or messages array")
            for message in messages:
                if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "system", "tool"}:
                    raise ValueError("Unknown message role")
                if not isinstance(message.get("content", ""), str):
                    raise TypeError("Message content must be text")
                lines.append(json.dumps(message, ensure_ascii=False))
        except (ValueError, TypeError) as error:
            raise ValueError(f"Invalid legacy transcript at line {number}: {error}. Original remains available for read-only inspection.") from error
    if not lines:
        raise ValueError("Legacy transcript is empty")
    return "Imported legacy transcript (quoted history; tool records are not replayed; incomplete pairs remain text):\n" + "\n".join(lines)
