from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexa_code.policy import Policy, Rule


def test_deny_precedes_bypass_and_plan_precedes_allow(workspace: Path) -> None:
    policy = Policy(workspace)
    args = {"file_path": "a.txt", "content": "hello"}
    policy.rules.append(Rule.exact("Write", args, workspace, "deny", "session"))
    policy.set_mode("bypass", confirmed=True)
    assert policy.decide("Write", args).decision == "deny"
    policy.rules.clear()
    policy.rules.append(Rule.exact("Write", args, workspace, "allow", "session"))
    policy.set_mode("plan")
    assert policy.decide("Write", args).decision == "deny"


def test_auto_asks_and_bypass_requires_current_process_opt_in(workspace: Path) -> None:
    policy = Policy(workspace, mode="auto")
    assert policy.decide("Write", {"file_path": "a", "content": "x"}).decision == "ask"
    with pytest.raises(ValueError, match="current session"):
        policy.set_mode("bypass")
    policy.set_mode("bypass", confirmed=True)
    assert policy.decide("Write", {"file_path": "a"}).decision == "allow"
    assert Policy(workspace, mode="bypass").mode == "default"


def test_rules_are_exact_workspace_and_arguments_scoped(workspace: Path) -> None:
    policy = Policy(workspace)
    args = {"file_path": "a", "content": "one"}
    rule = Rule.exact("Write", args, workspace, "allow", "persistent")
    policy.add(rule)
    assert Policy(workspace).decide("Write", args).decision == "allow"
    assert policy.decide("Write", {**args, "content": "two"}).decision == "ask"
    other = Policy(workspace / "other")
    other.rules.append(rule)
    assert other.decide("Write", args).decision == "ask"
    policy.remove(0)
    assert Policy(workspace).decide("Write", args).decision == "ask"


def test_read_outside_workspace_and_symlink_requires_approval(workspace: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    external = tmp_path_factory.mktemp("external") / "x"
    external.write_text("outside")
    (workspace / "link").symlink_to(external)
    policy = Policy(workspace)
    assert policy.decide("Read", {"file_path": "inside"}).decision == "allow"
    assert policy.decide("Read", {"file_path": "link"}).decision == "ask"
    assert policy.decide("Read", {"file_path": str(external)}).decision == "ask"
    (workspace / "directory-link").symlink_to(external.parent, target_is_directory=True)
    assert policy.decide("Glob", {"pattern": "**/*.txt", "path": ""}).decision == "ask"
    assert policy.decide("Grep", {"pattern": "secret", "path": ""}).decision == "ask"


def test_legacy_broad_allow_requires_migration_confirmation(workspace: Path) -> None:
    path = workspace / ".claude" / "settings.local.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"permissions": {"allow": ["Bash"], "deny": ["Write"]}, "permissionMode": "bypass"}))
    policy = Policy(workspace)
    assert policy.decide("Bash", {"command": "echo hi"}).decision == "ask"
    assert policy.decide("Write", {"file_path": "a"}).decision == "deny"
    assert policy.migration


def test_deferred_tool_cannot_launder_deny(workspace: Path) -> None:
    policy = Policy(workspace)
    args = {"file_path": "a", "content": "one"}
    policy.rules.append(Rule.exact("Write", args, workspace, "deny", "session"))
    decision = policy.decide("ExecuteExtraTool", {"tool_name": "Write", "params_json": json.dumps(args)})
    assert decision.decision == "deny"


def test_escaping_globs_and_global_skills_require_approval(workspace: Path) -> None:
    policy = Policy(workspace)
    assert policy.decide("Glob", {"pattern": "../*", "path": ""}).decision == "ask"
    assert policy.decide("Glob", {"pattern": "**/*.py", "path": ""}).decision == "allow"
    assert policy.decide("Skill", {"skill_name": "outside"}).decision == "ask"
    assert policy.decide("DiscoverSkills", {"query": ""}).decision == "ask"
