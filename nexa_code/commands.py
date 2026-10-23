"""User command routing; every model turn uses the same Session API."""

from __future__ import annotations

import importlib.metadata
import inspect
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.compiler import compile_file

from . import __version__
from .loader import DEFINITIONS

if TYPE_CHECKING:
    from .session import Session

COMMAND_NAMES = [
    "help",
    "clear",
    "compact",
    "model",
    "cost",
    "usage",
    "stats",
    "status",
    "context",
    "config",
    "vim",
    "fast",
    "rewind",
    "resume",
    "exit",
    "quit",
    "init",
    "doctor",
    "add-dir",
    "memory",
    "permissions",
    "agents",
    "copy",
    "export",
    "undo",
    "review",
    "share",
    "git",
    "mcp",
    "pr",
    "login",
    "feedback",
    "keybindings",
    "release-notes",
    "screenshot",
    "terminal-setup",
    "bug",
    "install",
    "plugin",
    "diff",
    "hooks",
    "history",
    "theme",
    "env",
    "version",
    "recap",
    "summary",
    "commit",
    "effort",
    "session",
]
PROMPTS = {
    "init": "Inspect this repository and propose an AGENTS.md file. Write it only after the Write tool is approved.",
    "review": "Review the current changes. Inspect files and run appropriate checks, then report actionable findings.",
    "pr": "Prepare a pull request for the current changes. Inspect Git state and repository instructions; request exact approval for external writes.",
    "commit": "Inspect the current diff and prepare the requested commit, following repository commit rules. Ask exact approval for the commit command.",
}


def doctor(workspace: Path) -> dict[str, Any]:
    runtime = importlib.metadata.version("nexa-lang")
    node = shutil.which("node")
    node_version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5, check=False).stdout.strip() if node else "missing"
    return {
        "nexa_code": __version__,
        "runtime": runtime,
        "runtime_source": str(Path(inspect.getfile(compile_file)).parent),
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "node": node_version,
        "node_supported": node_version.startswith("v") and int(node_version[1:].split(".")[0]) >= 20,
        "pnpm": bool(shutil.which("pnpm")),
        "uv": bool(shutil.which("uv")),
        "cwd": str(workspace),
        "source_present": (DEFINITIONS / "main.nx").is_file(),
        "prebuilt_python_required": False,
        "provider_credentials": {key: bool(os.environ.get(key)) for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "API_KEY")},
        "nxs_present_in_workspace": bool(list(workspace.glob("*.nxs"))),
        "configuration": "Runtime resolves .nxs from selected cwd and its parents; nearest scope wins. Values are never printed.",
        "distribution": "Source checkout: uv.lock uses ../../Nexa; wheel metadata pins released Nexa v2.4.0 at c2162637236e4a73feea410c4183672411666521.",
    }


def run_command(session: Session, line: str, *, reset_cancel: bool = True) -> str:
    name, _, argument = line.strip().lstrip("/").partition(" ")
    argument = argument.strip()
    if name not in COMMAND_NAMES:
        raise ValueError(f"Unknown command /{name}; use /help")
    if name in {"exit", "quit"}:
        return "__EXIT__"
    if name == "help":
        return "Nexa Code commands:\n" + "  ".join("/" + item for item in COMMAND_NAMES)
    if name in {"cost", "usage", "stats"}:
        return json.dumps({**session.usage(), "cost": "Token counts are measured; monetary prices are not configured."}, indent=2)
    if name in {"status", "session"}:
        return json.dumps(
            {
                "session_id": session.id,
                "run_id": session.state.run_id if session.state else None,
                "status": session.state.status.value if session.state else "ready",
                "model": session.agent.model,
                "provider": session.agent.provider_api,
                "cwd": str(session.workspace),
                "mode": session.policy.mode,
            },
            indent=2,
        )
    if name in {"doctor", "login", "env"}:
        return json.dumps(doctor(session.workspace), indent=2)
    if name == "clear":
        session.new()
        return "New session created. Previous checkpoints retained."
    if name == "model":
        if argument:
            session.new(model=argument)
            return "New session created for model " + argument
        from src.runtime.secrets import nexa_secrets

        names = list(dict.fromkeys([session.agent.model, *nexa_secrets.get_model_config().values()]))
        session.emit("model_list", current=session.agent.model, models=[{"name": item} for item in names])
        return "Current model: " + session.agent.model + "; /model <model> starts a new session"
    if name == "resume":
        return resume_command(session, argument, reset_cancel=reset_cancel)
    if name in {"history", "recap", "summary", "rewind", "compact"}:
        return history_command(session, name, argument)
    if name == "permissions":
        return permission_command(session, argument)
    if name == "config":
        return config_command(session, argument)
    if name in {"export", "share"}:
        require_write(session)
        path = (session.workspace / (argument or f"conversation-{session.id[:8]}.md")).resolve()
        path.write_text(transcript(session), encoding="utf-8")
        session.emit("artifact", name=path.name, path=str(path))
        return "Conversation exported to " + str(path)
    if name in PROMPTS:
        session.message(PROMPTS[name] + "\n" + argument, reset_cancel=reset_cancel)
        return ""
    if name in {"keybindings", "terminal-setup"}:
        return "Enter submit · Ctrl+J newline · Esc cancel · Ctrl+O expand tools · Tab complete · Up/Down history/picker · Shift+Tab default/plan/auto · Ctrl+C cancel/exit"
    if name in {"version", "release-notes"}:
        return f"Nexa Code {__version__}: runtime checkpoints, exact approvals, durable sessions, versioned JSON protocol. See docs/MIGRATION.md."
    if name in {"vim", "theme", "fast", "effort"}:
        if name == "fast" or name == "effort":
            return "Provider speed/reasoning controls are not supported by this host; choose a configured model with /model."
        session.emit("ui_setting", name=name, value=argument or ("toggle" if name == "vim" else "graphite"))
        return f"UI setting {name}: {argument or 'toggle'}"
    if name == "install":
        require_write(session)
        args = shlex.split(argument)
        if not args or args[0] not in {"python", "node"} or len(args) < 2:
            return "Usage: /install python <packages> (uv add) | /install node <packages> (pnpm add)"
        return execute(["uv", "add", *args[1:]] if args[0] == "python" else ["pnpm", "add", *args[1:]], session)
    if name == "git":
        args = shlex.split(argument) or ["status", "--short"]
        require_write(session)
        return execute(["git", *args], session)
    if name == "diff":
        if argument:
            require_write(session)
        return execute(["git", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", *shlex.split(argument)], session)
    if name == "undo":
        return undo(session, argument)
    if name == "hooks":
        return hooks(session, argument)
    from .aux_commands import dispatch

    return dispatch(session, name, argument)


def require_write(session: Session) -> None:
    if session.policy.mode == "plan":
        raise PermissionError("plan mode restricts this command; switch to default explicitly")


def execute(argv: list[str], session: Session) -> str:
    from .processes import run

    result = run(session, argv)
    return f"{result['stdout']}{result['stderr']}\n[exit code: {result['exit_code']}; {result['status']}]"


def transcript(session: Session) -> str:
    messages = session.state.messages if session.state else []
    return "# Nexa Code conversation\n\n" + "\n\n".join(f"## {item['role']}\n\n{item.get('content', '')}" for item in messages if item["role"] != "system")


def resume_command(session: Session, argument: str, *, reset_cancel: bool = True) -> str:
    if argument.startswith("resolve "):
        parts = argument.split(maxsplit=3)
        if len(parts) != 4 or parts[2] not in {"success", "failure"} or session.state is None:
            raise ValueError("Inspect the external effect, then /resume resolve <call_id> success|failure <observed evidence>")
        session.resolve(session.state.run_id, parts[1], parts[3], parts[2] == "success", reset_cancel=reset_cancel)
        return "Recorded the observed tool outcome and resumed the same run"
    if not argument or argument == "list":
        records = session.catalog.list_sessions()
        session.emit("session_list", sessions=records)
        return "\n".join(f"{item['id']}  {item['title']}" for item in records) or "No sessions"
    path = Path(argument).expanduser()
    if path.is_file():
        session.import_legacy(path)
        return "Legacy transcript imported into new session " + session.id + "; send a follow-up to continue"
    session.resume(argument, reset_cancel=reset_cancel)
    return "Resumed session " + session.id


def history_command(session: Session, name: str, argument: str) -> str:
    messages = session.state.messages if session.state else []
    listing = "\n".join(f"{index} [{item['role']}] {item.get('content', '')}" for index, item in enumerate(messages) if item["role"] != "system")
    if name == "rewind" and argument.isdigit():
        index = int(argument)
        if not 1 <= index < len(messages):
            raise ValueError("Rewind index is outside the message history")
        context = f"Forked transcript at message {index} (tool records are quoted, not replayed):\n{json.dumps(messages[1 : index + 1], ensure_ascii=False)}"
        session.new(transcript=context)
        return "Forked a new session at the selected transcript position"
    if name == "rewind" and argument.startswith("search "):
        return "\n".join(row for row in listing.splitlines() if argument[7:] in row)
    if name == "compact":
        if not argument:
            return "Usage: /compact <reviewed summary>. Creates a new session with your summary; original provider checkpoints remain intact."
        session.new(transcript="User-reviewed summary of the preceding session:\n" + argument)
        return "Created a new session from the reviewed summary"
    return listing or "No messages yet"


def permission_command(session: Session, argument: str) -> str:
    if argument:
        parts = argument.split()
        if parts[0] in {"default", "plan", "auto", "bypass"}:
            session.set_mode(parts[0], confirmed=parts[1:] == ["confirm"])
        elif len(parts) == 2 and parts[0] == "remove" and parts[1].isdigit():
            session.policy.remove(int(parts[1]))
        else:
            return "Use /permissions default|plan|auto, bypass confirm or remove <index>. Add exact session/persistent rules in the approval panel (s/p)."
    return json.dumps({"mode": session.policy.mode, "rules": [asdict(rule) for rule in session.policy.rules], "migration": session.policy.migration}, indent=2)


def config_command(session: Session, argument: str) -> str:
    from .settings import read, validate, write

    data = read(session.workspace)
    parts = argument.split(maxsplit=2)
    if parts and parts[0] == "set":
        require_write(session)
        if len(parts) != 3 or parts[1] not in {"theme", "editorMode", "max_model_calls", "max_tool_calls", "timeout"}:
            raise ValueError("Config keys: theme, editorMode, max_model_calls, max_tool_calls, timeout; credentials stay in .nxs/environment")
        value = json.loads(parts[2])
        data[parts[1]] = value
        validate(data)
        if parts[1] in {"max_model_calls", "max_tool_calls", "timeout"}:
            from dataclasses import replace

            session.config = replace(session.config, **{parts[1]: value})
        write(session.workspace, data)
        session.settings = data
        if parts[1] in {"theme", "editorMode"}:
            session.emit("ui_setting", name="vim" if parts[1] == "editorMode" else "theme", value=value)
    if parts and parts[0] == "get":
        return json.dumps(data.get(parts[1] if len(parts) > 1 else ""))
    return json.dumps(data, indent=2)


def undo(session: Session, argument: str) -> str:
    history = session.namespace.get("_CCPORT_FILE_HISTORY", {})
    if argument == "list":
        return json.dumps(history, indent=2)
    require_write(session)
    target = str((session.workspace / argument).resolve()) if argument else next((key for key in reversed(history) if history[key]), "")
    if not target or not history.get(target):
        return "No file snapshot to restore"
    backup = history[target].pop()
    shutil.copyfile(backup, target)
    if session.state:
        session.save(session.state)
    return "Restored " + target


def hooks(session: Session, argument: str) -> str:
    path = session.workspace / ".nexa-code" / "hooks.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    parts = argument.split(maxsplit=2)
    if len(parts) == 3 and parts[0] in {"add", "remove"}:
        require_write(session)
        commands = data.setdefault(parts[1], [])
        if parts[0] == "add":
            commands.append(parts[2])
        else:
            commands.remove(parts[2])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
    if len(parts) >= 2 and parts[0] == "test":
        require_write(session)
        return "\n".join(execute(["/bin/bash", "-c", command], session) for command in data.get(parts[1], []))
    return json.dumps({"hooks": data, "mode": "manual; /hooks test <event> runs configured commands. Legacy hooks require migration."}, indent=2)


def current_command(line: str) -> str:
    from .tool_services import current_session

    return run_command(current_session(), line)
