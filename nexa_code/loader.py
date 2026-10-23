"""Compile declarations on launch using the installed Nexa 2.4 compiler."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import io
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.compiler import compile_file
from src.runtime.agent import NexaAgent
from src.runtime.secrets import nexa_secrets

APP_ROOT = Path(__file__).resolve().parent.parent
DEFINITIONS = APP_ROOT / "src" if (APP_ROOT / "src" / "main.nx").exists() else Path(__file__).resolve().parent / "definitions"


def load_definitions(workspace: Path, *, model: str | None = None, provider_api: str = "chat") -> tuple[NexaAgent, dict[str, Any], str]:
    version = importlib.metadata.version("nexa-lang")
    if version.split(".")[:2] != ["2", "4"] or not hasattr(NexaAgent, "continue_run"):
        raise RuntimeError("Nexa Code needs the Nexa 2.4 runtime with NexaAgent.continue_run; see docs/INSTALL.md")
    definition = DEFINITIONS / "main.nx"
    signature = tuple((str(path), path.stat().st_mtime_ns) for path in sorted(DEFINITIONS.rglob("*.nx")))
    compilation = _compile(signature)
    digest = hashlib.sha256("".join(Path(path).read_text(encoding="utf-8") for path in compilation.sources).encode()).hexdigest()
    namespace: dict[str, Any] = {"__name__": "nexa_code.definitions", "__file__": str(workspace / ".nexa-code-entry.py")}
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(compilation.python_code, str(definition), "exec"), namespace)  # noqa: S102 - Load our installed .nx definitions through the public compiler.
    agent: NexaAgent = namespace["Coder"]
    requested_model = model or agent.model
    agent.model = nexa_secrets.get_model_config().get(requested_model, requested_model)
    agent.provider_api = provider_api
    # The runtime pauses at every exposed call; Policy makes a single exact decision.
    for tool in agent.tools:
        tool["requires_approval"] = True
        tool["_handler"] = namespace[tool["name"]]
    return agent, namespace, digest


@lru_cache(maxsize=2)
def _compile(signature: tuple[tuple[str, int], ...]) -> Any:
    return compile_file(DEFINITIONS / "main.nx")
