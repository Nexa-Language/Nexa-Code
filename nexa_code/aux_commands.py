"""Local utility commands with explicit state and platform effects."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .processes import run

if TYPE_CHECKING:
    from .session import Session


def dispatch(session: Session, name: str, argument: str) -> str:
    from .commands import doctor, require_write

    if name == "context":
        return session.namespace["build_user_context"](session.agent.model)
    if name == "memory":
        if argument.startswith("add "):
            session.namespace.setdefault("_CCPORT_MEMORY", []).append(argument[4:])
            if session.state:
                session.save(session.state)
        paths = [session.workspace / "AGENTS.md", session.workspace / "CLAUDE.md", session.workspace / ".claude" / "CLAUDE.md"]
        return json.dumps(
            {"memories": session.namespace.get("_CCPORT_MEMORY", []), "files": [{"path": str(path), "exists": path.is_file()} for path in paths]}, indent=2
        )
    if name == "add-dir":
        if argument:
            path = Path(argument).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise ValueError("Additional directory must be a directory")
            dirs = session.record.setdefault("additional_directories", [])
            if str(path) not in dirs:
                dirs.append(str(path))
            session.catalog.put(session.record)
        return json.dumps(
            {"references": session.record.get("additional_directories", []), "permissions": "Outside-workspace calls require exact approval"}, indent=2
        )
    if name == "agents":
        return f"Coder: {session.agent.model}, {len(session.agent.tools)} tools. Agent creates a checkpointed read-only research run; propose mutations to the parent."
    if name == "mcp":
        return mcp_config(session, argument)
    if name == "copy":
        require_write(session)
        return copy_message(session, argument)
    if name in {"bug", "feedback"}:
        require_write(session)
        path = session.workspace / f"nexa-{name}-{int(time.time())}.md"
        path.write_text(f"# Nexa Code {name}\n\n{argument}\n\n```json\n{json.dumps(doctor(session.workspace), indent=2)}\n```\n", encoding="utf-8")
        session.emit("artifact", name=path.name, path=str(path))
        return "Local report saved to " + str(path) + "; review before sharing"
    if name == "screenshot":
        require_write(session)
        return session.namespace["TerminalCapture"](argument)
    if name == "plugin":
        return "Plugin marketplace is unavailable. Local skills: Skill / DiscoverSkills; MCP servers: /mcp; packages: /install."
    raise ValueError("Unhandled command: " + name)


def copy_message(session: Session, argument: str) -> str:
    messages = session.state.messages if session.state else []
    texts = [item["content"] for item in reversed(messages) if item["role"] == "assistant" and isinstance(item.get("content"), str) and item["content"].strip()]
    index = int(argument or "1") - 1
    if not 0 <= index < len(texts):
        raise ValueError("Choose an available assistant message with /copy [N], starting at 1")
    text = texts[index]
    path = session.workspace / ".nexa-code" / "response.md"
    path.write_text(text, encoding="utf-8")
    command = "pbcopy" if sys.platform == "darwin" else "clip" if sys.platform == "win32" else "xclip"
    if not shutil.which(command):
        return "Clipboard unavailable; response saved to " + str(path)
    result = run(session, [command, *(["-selection", "clipboard"] if command == "xclip" else [])], timeout=5, input_text=text)
    return f"Clipboard exit={result['exit_code']}; response saved to {path}"


def mcp_config(session: Session, argument: str) -> str:
    from .commands import require_write

    path = session.workspace / ".mcp.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError(".mcp.json mcpServers must be an object")
    parts = argument.split(maxsplit=2)
    if parts and parts[0] in {"add", "remove"}:
        require_write(session)
        if len(parts) < 2:
            raise ValueError("Usage: /mcp add <name> <JSON config> | /mcp remove <name>")
        if parts[0] == "remove":
            del servers[parts[1]]
        else:
            if len(parts) < 3:
                raise ValueError('Usage: /mcp add <name> {"command":"...","args":[]}')
            spec = json.loads(parts[2])
            if not isinstance(spec, dict) or not (isinstance(spec.get("command"), str) or isinstance(spec.get("url"), str)):
                raise ValueError("MCP config requires command or url")
            servers[parts[1]] = spec
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return json.dumps(
        {
            "servers": [{"name": key, "transport": "http" if "url" in value else "stdio"} for key, value in servers.items()],
            "config": str(path),
            "usage": "MCPTool / ListMcpResources / ReadMcpResource; install uv sync --extra mcp",
        },
        indent=2,
    )
