"""Platform tool services; model execution and recovery stay in Nexa."""

from __future__ import annotations

import contextvars
import json
import os
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from src.runtime.artifacts import ArtifactStore
from src.runtime.tool_dispatch import ToolDispatcher

from .processes import run, start

if TYPE_CHECKING:
    from .session import Session

_CURRENT: contextvars.ContextVar[Session] = contextvars.ContextVar("nexa_code_session")


def current_session() -> Session:
    return _CURRENT.get()


@contextmanager
def active(session: Session) -> Generator[None, None, None]:
    token = _CURRENT.set(session)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def invoke(name: str, arguments: dict[str, Any]) -> str:
    session = _CURRENT.get()
    handlers = {
        "Bash": shell,
        "PowerShell": shell,
        "Agent": agent,
        "AskUserQuestion": question,
        "ExecuteExtraTool": deferred,
        "Artifact": artifact,
        "ReviewArtifact": review_artifact,
        "SendUserFile": send_file,
        "EnterPlanMode": plan,
        "ExitPlanMode": plan,
        "Sleep": sleep,
        "Monitor": monitor,
        "Config": config_tool,
        "REPL": platform,
        "PushNotification": platform,
        "TerminalCapture": platform,
        "EnterWorktree": worktree,
        "ExitWorktree": worktree,
    }
    if name in {"MCPTool", "ListMcpResources", "ReadMcpResource", "McpAuth"}:
        from .mcp_tools import invoke as mcp_invoke

        return mcp_invoke(session, name, arguments)
    return handlers[name](session, name, arguments)


def shell(session: Session, name: str, arguments: dict[str, Any]) -> str:
    command = str(arguments["command"])
    timeout = min(600.0, max(0.1, float(arguments.get("timeout") or 120000) / 1000))
    argv = (
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        if name == "PowerShell"
        else ["cmd", "/c", command]
        if os.name == "nt"
        else ["/bin/bash", "-c", command]
    )
    if arguments.get("run_in_background"):
        job = start(session, argv, timeout=timeout)
        return f"Started managed job {job.process.pid}; Monitor reads its result. Deadline: {timeout}s; jobs stop when this host exits."
    return json.dumps(run(session, argv, timeout=timeout), ensure_ascii=False)


def monitor(session: Session, name: str, arguments: dict[str, Any]) -> str:
    job_id = str(arguments["task_id"])
    job = session.jobs.get(job_id)
    if job is None:
        return "No managed process with this ID in the current host; processes are not restarted after exit."
    if not job.done.is_set():
        return "running"
    session.processes.pop(job_id, None)
    session.jobs.pop(job_id, None)
    return json.dumps(job.result())


def deferred(session: Session, name: str, arguments: dict[str, Any]) -> str:
    target = str(arguments["tool_name"])
    if target == "ExecuteExtraTool":
        raise ValueError("Recursive deferred execution is unsupported")
    args = json.loads(arguments["params_json"] or "{}")
    decision = session.policy.decide(target, args)
    if decision.decision == "deny":
        raise PermissionError(decision.provenance)
    outcome = ToolDispatcher.from_definitions(session.agent.tools).dispatch(target, args, approved=True)
    if outcome.status == "unknown":
        from src.runtime.tool_dispatch import ToolOutcomeUnknown

        raise ToolOutcomeUnknown(outcome.error)
    return outcome.text()


def agent(session: Session, name: str, arguments: dict[str, Any]) -> str:
    from src.runtime.agent import NexaAgent
    from src.runtime.run_state import RunConfig

    from .policy import READ_ONLY

    tools: list[dict[str, Any]] = [{**tool, "requires_approval": False} for tool in session.agent.tools if tool["name"] in READ_ONLY]
    child = NexaAgent(
        name="NexaCodeResearch",
        model=session.agent.model,
        provider_api=session.agent.provider_api,
        prompt="Research the requested task using read-only tools inside the workspace. Return findings and proposed changes.",
        tools=tools,
    )
    # Nested tools still resolve the same workspace policy, including deny rules.
    for tool in tools:
        handler = tool["_handler"]
        tool_name = tool["name"]

        def checked(*, _handler: Any = handler, _name: str = tool_name, **kwargs: Any) -> Any:
            decision = session.policy.decide(_name, kwargs)
            if decision.decision != "allow":
                raise PermissionError("Nested tool requires a separate top-level approval: " + decision.provenance)
            return _handler(**kwargs)

        tool["_handler"] = checked
    state = child.execute(
        arguments["prompt"],
        config=RunConfig(timeout=max(0.1, session.deadline - time.monotonic()), max_tool_calls=8, artifact_directory=session.config.artifact_directory),
        cancel=session.cancel,
        save=session.save_child,
        provider=session.provider,
    )
    return json.dumps(
        {
            "run_id": state.run_id,
            "status": state.status.value,
            "output": state.output,
            "error": state.error,
            "scope": "read-only research; request proposed mutations as top-level calls",
        },
        ensure_ascii=False,
    )


def question(session: Session, name: str, arguments: dict[str, Any]) -> str:
    questions = json.loads(arguments["questions"])
    if not isinstance(questions, list) or not questions:
        raise ValueError("questions must be a nonempty JSON array")
    for item in questions:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str) or not item["question"].strip():
            raise ValueError("Each question requires nonempty question text")
        options = item.get("options", [])
        if not isinstance(options, list) or any(not isinstance(option, dict) or not isinstance(option.get("label"), str) for option in options):
            raise ValueError("Question options must be objects with string labels")
    call_id = session.current_call_id
    session.emit("question", call_id=call_id, questions=questions)
    while not session.cancel.wait(0.05):
        if time.monotonic() >= session.deadline:
            return "Question deadline exceeded"
        with session.answer_lock:
            if call_id in session.answers:
                return session.answers.pop(call_id)
    return "Question cancelled"


def artifact(session: Session, name: str, arguments: dict[str, Any]) -> str:
    content = str(arguments["content"])
    store = ArtifactStore(session.config.artifact_directory)
    key = store.put(content)
    session.artifact_names[str(arguments["name"])] = key
    path = str(store.root / key)
    session.emit("artifact", artifact_id=key, name=arguments["name"], path=path, characters=len(content))
    return json.dumps({"artifact_id": key, "path": path, "characters": len(content)})


def review_artifact(session: Session, name: str, arguments: dict[str, Any]) -> str:
    target = str(arguments["name"])
    if not target:
        return json.dumps(session.artifact_names)
    key = session.artifact_names.get(target, target)
    return ArtifactStore(session.config.artifact_directory).read(key)


def send_file(session: Session, name: str, arguments: dict[str, Any]) -> str:
    path = (session.workspace / arguments["file_path"]).resolve()
    if not path.is_file():
        raise ValueError("File does not exist")
    session.emit("artifact", name=path.name, path=str(path), characters=path.stat().st_size)
    return f"Local file available: {path}"


def plan(session: Session, name: str, arguments: dict[str, Any]) -> str:
    mode = "plan" if name == "EnterPlanMode" else "default"
    session.set_mode(mode)
    return f"Permission mode: {mode}"


def sleep(session: Session, name: str, arguments: dict[str, Any]) -> str:
    seconds = min(60, max(0, float(arguments["seconds"])))
    cancelled = session.cancel.wait(min(seconds, max(0, session.deadline - time.monotonic())))
    return "cancelled" if cancelled else f"Slept {seconds}s"


def config_tool(session: Session, name: str, arguments: dict[str, Any]) -> str:
    from .commands import config_command

    action = arguments["action"] or "list"
    if action not in {"get", "set", "list"}:
        raise ValueError("Config action must be get, set or list")
    return config_command(session, f"{action} {arguments['key']} {arguments['value']}".strip())


def platform(session: Session, name: str, arguments: dict[str, Any]) -> str:
    if name == "REPL":
        return json.dumps(run(session, [sys.executable, "-c", arguments["code"]], timeout=30))
    if name == "PushNotification":
        title, message = arguments["title"] or "Nexa Code", arguments["message"]
        if sys.platform == "darwin":
            script = f"display notification {json.dumps(message, ensure_ascii=False)} with title {json.dumps(title, ensure_ascii=False)}"
            argv = ["osascript", "-e", script]
        else:
            argv = ["msg", "*", f"{title}: {message}"] if os.name == "nt" else ["notify-send", title, message]
        return json.dumps(run(session, argv, timeout=10))
    path = (session.workspace / (arguments["file_path"] or f"screenshot-{int(time.time())}.png")).resolve()
    if os.name == "nt":
        return "Use Windows Snipping Tool to capture a file, then SendUserFile to display it."
    argv = ["screencapture", "-x", str(path)] if sys.platform == "darwin" else ["import", "-window", "root", str(path)]
    result = run(session, argv, timeout=10)
    if result["exit_code"] == 0 and path.is_file():
        session.emit("artifact", name=path.name, path=str(path))
    return json.dumps(result)


def worktree(session: Session, name: str, arguments: dict[str, Any]) -> str:
    branch = arguments["branch"].strip()
    path = arguments["path"].strip() or (".worktrees/" + branch if branch else "")
    if not path or name == "EnterWorktree" and not branch:
        raise ValueError("A worktree path and, when creating, a branch are required")
    argv = ["git", "worktree", "add", "-b", branch, "--", path] if name == "EnterWorktree" else ["git", "worktree", "remove", "--", path]
    return json.dumps(
        {
            **run(session, argv, timeout=30),
            "workspace": str(session.workspace),
            "note": "Open a new host in the worktree to select it. Branches and dirty files are retained on removal failure.",
        }
    )
