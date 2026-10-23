"""One permission decision boundary, scoped to an explicit workspace."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

DecisionName = Literal["allow", "deny", "ask"]
READ_ONLY = {
    "Read",
    "Glob",
    "Grep",
    "TaskList",
    "TaskGet",
    "SearchExtraTools",
    "Skill",
    "VerifyPlan",
    "CtxInspect",
    "DiscoverSkills",
    "Monitor",
    "LocalMemoryRecall",
    "ListPeers",
    "ReviewArtifact",
    "CronList",
}
MODES = {"default", "plan", "auto", "bypass"}


@dataclass(frozen=True)
class Decision:
    decision: DecisionName
    provenance: str


@dataclass(frozen=True)
class Rule:
    tool: str
    workspace: str
    arguments: dict[str, Any]
    decision: DecisionName
    scope: str
    match: str = "exact"

    @classmethod
    def exact(cls, tool: str, arguments: dict[str, Any], workspace: Path, decision: DecisionName, scope: str) -> Rule:
        return cls(tool, str(workspace.resolve()), json.loads(json.dumps(arguments, sort_keys=True, allow_nan=False)), decision, scope)

    def matches(self, tool: str, arguments: dict[str, Any], workspace: Path) -> bool:
        if self.workspace != str(workspace.resolve()) or self.tool != tool:
            return False
        if self.match == "legacy_deny":
            pattern = self.arguments.get("pattern")
            return pattern is None or any(fnmatch.fnmatchcase(str(value), str(pattern).replace(":*", "*")) for value in arguments.values())
        return self.arguments == arguments


class Policy:
    def __init__(self, workspace: Path, *, mode: str = "default") -> None:
        self.workspace = workspace.resolve()
        self.path = self.workspace / ".nexa-code" / "policy.json"
        self.mode = "default"
        self.rules: list[Rule] = []
        self.migration: list[str] = []
        self._load()
        if mode == "bypass":
            self.migration.append("Stored bypass requires /permissions bypass confirm in the current session")
        else:
            self.set_mode(mode)

    def _load(self) -> None:
        if self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != 1 or not isinstance(payload.get("rules"), list):
                raise ValueError("Invalid .nexa-code/policy.json schema")
            for value in payload["rules"]:
                rule = Rule(**value)
                if rule.decision not in {"allow", "deny", "ask"} or rule.match != "exact" or rule.scope != "persistent":
                    raise ValueError("Persistent rules require exact arguments and a valid decision")
                self.rules.append(rule)
        paths = [Path.home() / ".claude" / "settings.json", self.workspace / ".claude" / "settings.json", self.workspace / ".claude" / "settings.local.json"]
        for path in paths:
            if not path.exists():
                continue
            value = json.loads(path.read_text(encoding="utf-8"))
            permissions = value.get("permissions", {})
            for rule in permissions.get("deny", []):
                match = re.fullmatch(r"([^()]+)(?:\((.*)\))?", str(rule))
                if match:
                    self.rules.append(Rule(match[1], str(self.workspace), {"pattern": match[2]}, "deny", str(path), "legacy_deny"))
            for rule in permissions.get("allow", []):
                self.migration.append(f"Confirm a scoped replacement for legacy allow {rule} from {path}")
            if value.get("permissionMode") == "bypass" or permissions.get("defaultMode") == "bypass":
                self.migration.append(f"Stored bypass from {path} requires current-session opt-in")

    def set_mode(self, mode: str, *, confirmed: bool = False) -> None:
        if mode not in MODES:
            raise ValueError("Mode must be default, plan, auto or bypass")
        if mode == "bypass" and not confirmed:
            raise ValueError("bypass needs explicit confirmation in the current session")
        self.mode = mode

    def add(self, rule: Rule) -> None:
        if rule.workspace != str(self.workspace) or rule.match != "exact" or rule.scope not in {"session", "persistent"}:
            raise ValueError("Rules must be exact and scoped to this workspace")
        self.rules.append(rule)
        if rule.scope == "persistent":
            self._save()

    def remove(self, index: int) -> None:
        if not 0 <= index < len(self.rules):
            raise ValueError("Rule index is outside the displayed rules")
        if self.rules[index].scope not in {"session", "persistent"}:
            raise ValueError("Edit the original legacy settings file to remove its deny rule")
        self.rules.pop(index)
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": 1, "rules": [asdict(item) for item in self.rules if item.scope == "persistent"]}, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def decide(self, tool: str, arguments: dict[str, Any]) -> Decision:
        if tool == "ExecuteExtraTool":
            try:
                nested = json.loads(arguments.get("params_json", "{}"))
            except (ValueError, TypeError):
                return Decision("deny", "Invalid deferred arguments: params_json must be a JSON object")
            name = arguments.get("tool_name", "")
            if not isinstance(nested, dict) or not isinstance(name, str) or name == "ExecuteExtraTool":
                return Decision("deny", "Invalid recursive deferred call")
            outer = self._decide(tool, arguments)
            inner = self._decide(name, nested)
            if outer.decision == "deny" or inner.decision == "deny":
                return Decision("deny", f"Deferred target: {inner.provenance}; outer: {outer.provenance}")
            return inner if outer.decision == "allow" else outer
        return self._decide(tool, arguments)

    def _decide(self, tool: str, arguments: dict[str, Any]) -> Decision:
        matching = [rule for rule in self.rules if rule.matches(tool, arguments, self.workspace)]
        denied = next((rule for rule in matching if rule.decision == "deny"), None)
        if denied:
            return Decision("deny", f"deny rule ({denied.scope}) in {denied.workspace}")
        if self.mode == "plan" and tool not in READ_ONLY | {"ExitPlanMode", "AskUserQuestion", "EnterPlanMode"}:
            return Decision("deny", "plan mode permits read-only tools")
        allowed = next((rule for rule in matching if rule.decision == "allow"), None)
        if allowed:
            return Decision("allow", f"exact arguments ({allowed.scope}) in {allowed.workspace}")
        if any(rule.decision == "ask" for rule in matching):
            return Decision("ask", "explicit ask rule")
        if self.mode == "bypass":
            return Decision("allow", "current-session bypass opt-in; runtime sandbox remains enforced")
        if tool in READ_ONLY - {"Skill", "DiscoverSkills"} and self._local_paths(tool, arguments):
            return Decision("allow", "read-only tool inside selected workspace")
        return Decision("ask", "exact call requires approval")

    def _local_paths(self, tool: str, arguments: dict[str, Any]) -> bool:
        for key in ("file_path", "notebook_path", "path"):
            value = arguments.get(key)
            if value:
                path = (self.workspace / Path(str(value)).expanduser()).resolve()
                if not path.is_relative_to(self.workspace):
                    return False
        if tool == "Glob" and "pattern" in arguments:
            pattern = Path(str(arguments["pattern"]))
            if (".." in pattern.parts or pattern.is_absolute()) and not (self.workspace / pattern).resolve().is_relative_to(self.workspace):
                return False
        if tool in {"Glob", "Grep"}:
            base = (self.workspace / str(arguments.get("path") or ".")).resolve()
            # Recursive search implementations can dereference file or directory links.
            # Inspect links without descending into their targets before auto-allowing.
            for root, directories, files in os.walk(base, followlinks=False):
                for name in directories + files:
                    child = Path(root) / name
                    if child.is_symlink() and not child.resolve().is_relative_to(self.workspace):
                        return False
        return True
