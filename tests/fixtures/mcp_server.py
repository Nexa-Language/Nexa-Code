"""Offline stdio fixture exercised through the installed official SDK."""

import os
from pathlib import Path

from mcp.server import MCPServer

server = MCPServer("nexa-code-fixture", log_level="WARNING")
Path(os.environ["NEXA_MCP_PID"]).write_text(str(os.getpid()))


@server.tool()
def echo(value: str) -> str:
    return "fixture:" + value


@server.resource("note://hello")
def note() -> str:
    return "fixture resource"


server.run(transport="stdio")
