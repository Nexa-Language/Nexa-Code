"""MCP SDK 2.x transport; each approved request owns and closes its connection."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import Session


def configuration(session: Session) -> dict[str, Any]:
    path = session.workspace / ".mcp.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise TypeError(".mcp.json mcpServers must be an object")
    return servers


def invoke(session: Session, name: str, arguments: dict[str, Any]) -> str:
    servers = configuration(session)
    server = arguments["server"]
    if name == "McpAuth":
        if server not in servers:
            raise ValueError("MCP server is not configured")
        return "Browser OAuth is unavailable in this terminal host. Authorize with the server's supported client, then configure its stdio credentials."
    targets = [server] if server else list(servers)
    if name != "ListMcpResources" and not server:
        raise ValueError("A specific MCP server is required")
    output = []
    for target in targets:
        if target not in servers:
            raise ValueError("MCP server is not configured: " + target)
        output.append({"server": target, "result": asyncio.run(request(session, servers[target], name, arguments))})
    return json.dumps(output, ensure_ascii=False)


async def request(session: Session, config: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        from mcp import Client, StdioServerParameters
    except ImportError as error:
        raise RuntimeError("Install the MCP extra with uv sync --extra mcp") from error

    target = (
        config["url"]
        if "url" in config
        else StdioServerParameters(command=config["command"], args=config.get("args", []), env={**os.environ, **config.get("env", {})}, cwd=session.workspace)
    )
    end = min(session.deadline, time.monotonic() + 30)

    async def operation() -> dict[str, Any]:
        async with Client(target, read_timeout_seconds=max(0.1, end - time.monotonic()), cache=None) as client:
            if name == "MCPTool":
                params = json.loads(arguments["arguments"] or "{}")
                if not isinstance(params, dict):
                    raise ValueError("MCP tool arguments must be an object")
                try:
                    result = await client.call_tool(arguments["tool_name"], params)
                except Exception as error:
                    from src.runtime.tool_dispatch import ToolOutcomeUnknown

                    raise ToolOutcomeUnknown("MCP tool outcome is unknown; reconcile before retrying") from error
                if result.is_error:
                    raise RuntimeError(result.model_dump_json(exclude_none=True))
            elif name == "ReadMcpResource":
                result = await client.read_resource(arguments["uri"])
            else:
                result = await client.list_resources()
            return result.model_dump(exclude_none=True, by_alias=True)

    task = asyncio.create_task(operation())
    try:
        while not task.done():
            if session.cancel.is_set() or time.monotonic() >= end:
                raise TimeoutError("MCP request cancelled or timed out; reconcile any external tool effects before retrying")
            await asyncio.wait({task}, timeout=0.05)
        return await task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
