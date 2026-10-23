"""Session orchestration over the public Nexa execution/checkpoint interfaces."""

from __future__ import annotations

import copy
import difflib
import json
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.runtime.providers import ModelProvider
from src.runtime.run_state import RunConfig, RunState, RunStatus

from .loader import load_definitions
from .policy import Policy, Rule
from .processes import Job, terminate
from .protocol import Emitter
from .settings import read as read_settings
from .storage import Sessions, read_legacy
from .tool_services import active

PERSISTED_GLOBALS = (
    "_CCPORT_TASKS",
    "_CCPORT_TODOS",
    "_CCPORT_READ_STATE",
    "_CCPORT_FILE_HISTORY",
    "_CCPORT_MEMORY",
    "_CCPORT_GOAL",
    "_CCPORT_CRONS",
    "_CCPORT_MESSAGES",
)


class Session:
    def __init__(
        self,
        workspace: Path,
        *,
        session_id: str | None = None,
        provider: ModelProvider | None = None,
        config: RunConfig | None = None,
        emitter: Emitter | None = None,
        model: str | None = None,
        provider_api: str = "chat",
        mode: str = "default",
    ) -> None:
        self.workspace = workspace.resolve()
        if Path.cwd().resolve() != self.workspace:
            raise ValueError("Host must start in its explicit workspace")
        self.emitter = emitter or Emitter()
        self.provider = provider
        self.cancel = threading.Event()
        self.answer_lock = threading.Lock()
        self.answers: dict[str, str] = {}
        self.processes: dict[str, subprocess.Popen[str]] = {}
        self.jobs: dict[str, Job] = {}
        self.current_call_id = ""
        self.deadline = float("inf")
        self.artifact_names: dict[str, str] = {}
        self.policy = Policy(self.workspace, mode=mode)
        self.settings = read_settings(self.workspace)
        self.config = config or RunConfig(
            timeout=self.settings.get("timeout", 300),
            max_model_calls=self.settings.get("max_model_calls", 30),
            max_tool_calls=self.settings.get("max_tool_calls", 25),
        )
        self.config = replace(self.config, artifact_directory=str(self.workspace / ".nexa-code" / "artifacts"))
        self.catalog = Sessions(self.workspace / ".nexa-code" / "sessions.sqlite3")
        self.store = self.catalog.checkpoints
        self.agent, self.namespace, self.definition = load_definitions(self.workspace, model=model, provider_api=provider_api)
        self.namespace["set_permission_mode"] = self.set_mode
        self.namespace["_CCPORT_MODE"] = self.policy.mode
        self.state: RunState | None = None
        self.record = self.catalog.get(session_id) if session_id else self.catalog.create(self.workspace, self.agent.model, provider_api, self.definition)
        self._activate()

    @property
    def id(self) -> str:
        return self.record["id"]

    def _activate(self) -> None:
        expected = (str(self.workspace), self.agent.model, self.agent.provider_api, self.definition)
        actual = tuple(self.record[key] for key in ("workspace", "model", "provider", "definition"))
        if expected != actual:
            raise ValueError("Session workspace/model/provider/definitions changed; create a new session with /clear or /model")
        self.emitter.session_id = self.id
        for key in PERSISTED_GLOBALS:
            self.namespace.pop(key, None)
        self.artifact_names = {}
        self.agent.messages = []
        runs = self.catalog.runs(self.id)
        self.state = runs[-1] if runs else None
        if self.state:
            self.namespace.update(copy.deepcopy(self.state.metadata.get("tool_state", {})))
            self.artifact_names = copy.deepcopy(self.state.metadata.get("artifacts", {}))
            self.agent.messages = copy.deepcopy(self.state.messages)
        self.emit("session_info", cwd=str(self.workspace), model=self.agent.model, mode=self.policy.mode, checkpoint=self.state.run_id if self.state else None)
        messages = []
        for item in self.state.messages if self.state else []:
            if item["role"] not in {"user", "assistant"} or not isinstance(item.get("content"), str) or not item["content"]:
                continue
            content = item["content"]
            if not messages and item["role"] == "user" and "\n\nCurrent user request:\n" in content:
                content = content.split("\n\nCurrent user request:\n", 1)[1]
            messages.append({"role": item["role"], "content": content})
        self.emit("session_history", messages=[{**item, "content": item["content"][:8000]} for item in messages[-40:]])

    def emit(self, kind: str, *, call_id: str | None = None, **data: Any) -> None:
        self.emitter.emit(kind, run_id=self.state.run_id if self.state else None, call_id=call_id, **data)

    def save(self, state: RunState) -> None:
        self.state = state
        state.metadata.update(
            {
                "session_id": self.id,
                "tool_state": copy.deepcopy({key: self.namespace[key] for key in PERSISTED_GLOBALS if key in self.namespace}),
                "artifacts": copy.deepcopy(self.artifact_names),
            }
        )
        if "legacy_source" in self.record:
            state.metadata["legacy_source"] = self.record["legacy_source"]
        self.store.save(state)

    def save_child(self, state: RunState) -> None:
        state.metadata["parent_session_id"] = self.id
        if self.state:
            state.metadata["parent_run_id"] = self.state.run_id
        self.store.save(state)

    def on_event(self, event: dict[str, Any]) -> None:
        self.emit("runtime_event", event=event)
        if event["event"] == "tool_started":
            self.current_call_id = event["call_id"]
            call = next(item for item in self.state.pending_calls if item["id"] == self.current_call_id) if self.state else None
            arguments = json.loads(call["function"]["arguments"]) if call else {}
            self._snapshot(event["tool"], arguments)
            self.emit("tool_call", call_id=self.current_call_id, name=event["tool"], args=arguments)
        if event["event"] == "tool_completed" and self.state:
            journal = self.state.tool_journal[event["call_id"]]
            self.emit("tool_result", call_id=event["call_id"], name=journal["tool"], result=journal["content"], success=journal["success"])
            try:
                artifact = json.loads(journal["content"])
            except (json.JSONDecodeError, TypeError):
                return
            if isinstance(artifact, dict) and "artifact_id" in artifact:
                self.emit("artifact", **artifact)

    def _callbacks(self) -> dict[str, Any]:
        return {
            "cancel": self.cancel,
            "save": self.save,
            "on_event": self.on_event,
            "on_text": lambda text: self.emit("assistant_token", content=text) if text else None,
            "provider": self.provider,
        }

    def message(self, content: str, *, reset_cancel: bool = True) -> RunState:
        if not content.strip():
            raise ValueError("Message must not be empty")
        if self.state and self.state.status in {RunStatus.RUNNING, RunStatus.WAITING_APPROVAL}:
            raise ValueError("Resume, approve or cancel the pending run before sending a new message")
        if reset_cancel:
            self.cancel = threading.Event()
        self.record["title"] = self.record["title"] if self.state else content[:100]
        self.catalog.put(self.record)
        self.deadline = time.monotonic() + self.config.timeout
        with active(self):
            if self.state:
                state = self.agent.continue_run(self.state, content, config=self.config, **self._callbacks())
            else:
                initial = self.namespace["build_user_context"](self.agent.model) + "\n" + self.record.get("transcript", "")
                state = self.agent.execute(initial + "\n\nCurrent user request:\n" + content, config=self.config, **self._callbacks())
            return self._settle(state)

    def _settle(self, state: RunState) -> RunState:
        self.state = state
        # These resumes only apply policy decisions to runtime-paused calls; no model loop lives here.
        while state.status == RunStatus.WAITING_APPROVAL:
            call = state.pending_calls[0]
            name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"])
            decision = self.policy.decide(name, arguments)
            if decision.decision == "ask":
                self.emit(
                    "permission_request",
                    call_id=call["id"],
                    request_id=call["id"],
                    tool=name,
                    args=arguments,
                    cwd=str(self.workspace),
                    provenance=decision.provenance,
                    mode=self.policy.mode,
                    diff=self._diff(name, arguments),
                )
                break
            state = self.store.approve(state.run_id, call["id"], decision.decision == "allow")
            state.metadata.setdefault("policy_decisions", {})[call["id"]] = {"decision": decision.decision, "provenance": decision.provenance}
            self.save(state)
            state = self.agent.execute(state=state, **self._callbacks())
            self.state = state
        self.agent.messages = state.messages
        self.emit(
            "run_state",
            status=state.status.value,
            error=state.error,
            model_calls=state.model_calls,
            tool_calls=state.tool_calls,
            elapsed=state.elapsed,
            usage={"input_tokens": state.input_tokens, "output_tokens": state.output_tokens},
            limits=state.config,
        )
        if state.status != RunStatus.WAITING_APPROVAL:
            self.emit("done", reply=state.output, status=state.status.value, error=state.error)
            unresolved = [call_id for call_id, entry in state.tool_journal.items() if entry["status"] == "started"]
            if unresolved:
                self.emit(
                    "info",
                    message="Inspect the external effect before continuing. Record the observed result with /resume resolve "
                    + unresolved[0]
                    + " success|failure <observed evidence>.",
                )
        return state

    def approve(self, run_id: str, call_id: str, decision: str, *, reset_cancel: bool = True) -> RunState:
        if not self.state or self.state.run_id != run_id:
            raise ValueError("Approval does not refer to the current session run")
        state = self.store.load(run_id)
        if state.status != RunStatus.WAITING_APPROVAL or not state.pending_calls or state.pending_calls[0]["id"] != call_id:
            raise ValueError("Approval must match the displayed pending call")
        if decision not in {"deny", "allow_once", "allow_session", "allow_rule"}:
            raise ValueError("Invalid approval decision")
        call = state.pending_calls[0]
        name, arguments = call["function"]["name"], json.loads(call["function"]["arguments"])
        allowed = decision != "deny"
        policy = self.policy.decide(name, arguments)
        if allowed and policy.decision == "deny":
            raise ValueError("Policy denies this call: " + policy.provenance)
        if decision in {"allow_session", "allow_rule"}:
            self.policy.add(Rule.exact(name, arguments, self.workspace, "allow", "session" if decision == "allow_session" else "persistent"))
        state = self.store.approve(run_id, call_id, allowed)
        state.metadata.setdefault("policy_decisions", {})[call_id] = {"decision": decision, "provenance": "explicit user approval", "arguments": arguments}
        self.save(state)
        return self.resume(reset_cancel=reset_cancel)

    def resume(self, session_id: str | None = None, *, reset_cancel: bool = True) -> RunState:
        if session_id and session_id != self.id:
            self._require_settled()
            self._switch(self.catalog.get(session_id))
        if self.state is None:
            raise ValueError("Session has no checkpoint; send a message")
        if reset_cancel:
            self.cancel = threading.Event()
        self.deadline = time.monotonic() + max(0, RunConfig(**self.state.config).timeout - max(self.state.elapsed, time.time() - self.state.created_at))
        with active(self):
            return self._settle(self.agent.execute(state=self.state, **self._callbacks()))

    def cancel_pending(self) -> None:
        self.request_cancel()
        if self.state and self.state.status == RunStatus.WAITING_APPROVAL:
            with active(self):
                self._settle(self.agent.execute(state=self.state, **self._callbacks()))

    def request_cancel(self) -> None:
        self.cancel.set()
        for job in list(self.jobs.values()):
            job.cancel.set()

    def resolve(self, run_id: str, call_id: str, content: str, success: bool, *, reset_cancel: bool = True) -> RunState:
        if not self.state or self.state.run_id != run_id:
            raise ValueError("Resolution must refer to the current session run")
        self.state = self.store.resolve_tool(run_id, call_id, content, success=success)
        return self.resume(reset_cancel=reset_cancel)

    def import_legacy(self, path: Path) -> str:
        self._require_settled()
        transcript = read_legacy(path.resolve())
        record = self.catalog.create(
            self.workspace,
            self.agent.model,
            self.agent.provider_api,
            self.definition,
            transcript=transcript,
            legacy_source=str(path.resolve()),
            legacy_format="jsonl-v1",
        )
        self._switch(record)
        return self.id

    def new(self, model: str | None = None, provider_api: str | None = None, transcript: str = "") -> None:
        self._require_settled()
        if model or provider_api:
            self.agent, self.namespace, self.definition = load_definitions(
                self.workspace, model=model or self.agent.model, provider_api=provider_api or self.agent.provider_api
            )
        self._switch(self.catalog.create(self.workspace, self.agent.model, self.agent.provider_api, self.definition, transcript=transcript))

    def _switch(self, record: dict[str, Any]) -> None:
        expected = (str(self.workspace), self.agent.model, self.agent.provider_api, self.definition)
        if tuple(record[key] for key in ("workspace", "model", "provider", "definition")) != expected:
            raise ValueError("Session workspace/model/provider/definitions changed; start a matching host or import its transcript")
        self.record = record
        self.policy.rules = [rule for rule in self.policy.rules if rule.scope != "session"]
        if self.policy.mode == "bypass":
            self.set_mode("default")
        self.namespace["set_permission_mode"] = self.set_mode
        self.namespace["_CCPORT_MODE"] = self.policy.mode
        self._activate()

    def _require_settled(self) -> None:
        if self.state and (
            self.state.status in {RunStatus.RUNNING, RunStatus.WAITING_APPROVAL}
            or any(entry["status"] == "started" for entry in self.state.tool_journal.values())
        ):
            raise ValueError("Finish/cancel the pending run and resolve unknown outcomes before switching sessions")

    def usage(self) -> dict[str, int]:
        runs = self.catalog.runs(self.id, include_children=True)
        return {key: sum(getattr(state, key) for state in runs) for key in ("input_tokens", "output_tokens", "model_calls", "tool_calls")}

    def set_mode(self, mode: str, confirmed: bool = False) -> str:
        self.policy.set_mode(mode, confirmed=confirmed)
        self.namespace["_CCPORT_MODE"] = mode
        self.emit("mode_changed", mode=mode)
        return mode

    def close(self) -> bool:
        self.request_cancel()
        clean = True
        for job in list(self.jobs.values()):
            try:
                if not job.done.wait(timeout=2):
                    terminate(job.process)
                    job.done.wait(timeout=1)
                if job.error:
                    raise job.error
                clean = clean and job.done.is_set()
            except Exception as error:  # noqa: BLE001 - Report every failed cleanup while closing the remaining jobs.
                clean = False
                self.emit("error", code="PROCESS_CLEANUP_FAILED", message=str(error))
        self.jobs.clear()
        self.processes.clear()
        return clean

    def _snapshot(self, name: str, arguments: dict[str, Any]) -> None:
        if name == "ExecuteExtraTool":
            return self._snapshot(arguments["tool_name"], json.loads(arguments["params_json"]))
        if name not in {"Write", "Edit", "MultiEdit", "NotebookEdit"} or self.state is None:
            return
        path = (self.workspace / arguments.get("file_path", arguments.get("notebook_path", ""))).resolve()
        if not path.is_file():
            return
        folder = self.workspace / ".nexa-code" / "snapshots" / self.state.run_id
        folder.mkdir(parents=True, exist_ok=True)
        # Provider call IDs are opaque data, never filesystem path components.
        import hashlib

        backup = folder / hashlib.sha256(self.current_call_id.encode()).hexdigest()
        if backup.exists():
            return
        shutil.copyfile(path, backup)
        self.namespace.setdefault("_CCPORT_FILE_HISTORY", {}).setdefault(str(path), []).append(str(backup))
        self.save(self.state)

    def _diff(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in {"Write", "Edit", "MultiEdit"}:
            return ""
        path = (self.workspace / str(arguments.get("file_path", ""))).resolve()
        if not path.is_relative_to(self.workspace) or path.name.startswith(".env") or path.suffix == ".nxs":
            return "Preview unavailable for this path; inspect the exact parameters."
        try:
            before = path.read_text(encoding="utf-8", errors="replace") if path.is_file() and path.stat().st_size < 1_000_000 else ""
            after = str(arguments.get("content", before))
            if name == "Edit":
                after = before.replace(arguments["old_string"], arguments["new_string"], -1 if arguments.get("replace_all") else 1)
            if name == "MultiEdit":
                for edit in json.loads(arguments["edits"]):
                    after = after.replace(edit["old_string"], edit["new_string"], -1 if edit.get("replace_all") else 1)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return "Preview unavailable: inspect the exact arguments before approving or denying."
        return "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=str(path), tofile=str(path)))[:10000]
