from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from src.open_programs.model import ApprovalState, FileChange, PreservedFile, ProgramError, SnapshotFile
from src.open_programs.reuse import CapsuleOrigin

from nexa_code.fixture_provider import FixtureProvider
from nexa_code.open_program import OpenConfig, OpenProgram

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "open-programs"


@pytest.mark.oci
@pytest.mark.timeout(120)
def test_native_oci_proposal_explicit_grant_apply_replay_and_stale_evidence(tmp_path: Path) -> None:
    source, environment = tmp_path / "maintain.nx", tmp_path / "environment.json"
    shutil.copyfile(FIXTURES / "maintain.nx", source)
    shutil.copyfile(FIXTURES / "environment.json", environment)
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a - b\n")
    provider = FixtureProvider.load(FIXTURES / "replies.json")
    client = OpenProgram(OpenConfig(source, environment, tmp_path / "state.db", "maintain", tmp_path), provider=provider)
    try:
        report = client.check()
        assert report.ok and not provider.requests
        head = client.build(expected_revision=None, source_digest=report.source_digest)
        assert not provider.requests
        assert client.build(expected_revision=head.revision, source_digest=report.source_digest, locked=True) == head
        assert not provider.requests
        activity, result, proposal = client.maintain(["calc.py"], "Fix add", expected_revision=head.revision, source_digest=report.source_digest)
        assert result.status == "accepted", result.model_dump()
        assert proposal and "return a + b" in proposal.diff
        assert "return a - b" in target.read_text()
        evidence = client.inspect_proposal(proposal.digest)
        assert evidence["admission"]["accepted"]
        assert len(provider.requests) == 1
        with pytest.raises(ProgramError, match="confirmation_required"):
            client.approve(proposal.digest, actor="fixture-user", confirmed=False)
        grant = client.approve(proposal.digest, actor="fixture-user", confirmed=True)
        assert client.status()["proposals"][0]["proposal_id"] == proposal.digest
        assert client.status()["grants"][0]["grant_id"] == grant.digest
        with pytest.raises(ProgramError, match="approval_invalid"):
            client.apply(proposal.digest, "legacy-allow-session")
        expired = grant.model_copy(update={"expires_at": time.time() - 1})
        client.store.set_reference("approval:" + expired.digest, None, ApprovalState(grant=expired))
        with pytest.raises(ProgramError, match="approval_expired"):
            client.apply(proposal.digest, expired.digest)
        target.write_text("# user edit\n")
        with pytest.raises(ProgramError, match="workspace_conflict"):
            client.apply(proposal.digest, grant.digest)
        target.write_text("def add(a, b):\n    return a - b\n")
        assert client.apply(proposal.digest, grant.digest).state == "applied"
        assert target.read_text() == "def add(a, b):\n    return a + b\n"
        capsule = client.export_capsule(tmp_path / "repair.capsule.json", activity, CapsuleOrigin(source="fixture", creator="fixture-user", license="MIT"))
        assert client.import_capsule(tmp_path / "repair.capsule.json").digest == capsule.digest
        client.store.put(proposal.evidence[0].model_copy(update={"passed": False, "issued_at": time.time()}))
        with pytest.raises(ProgramError, match="evidence_stale"):
            client.approve(proposal.digest, actor="fixture-user", confirmed=True)
    finally:
        client.close()


@pytest.mark.oci
@pytest.mark.timeout(120)
def test_interrupted_native_apply_requires_recovery_and_explicit_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, environment = tmp_path / "maintain.nx", tmp_path / "environment.json"
    shutil.copyfile(FIXTURES / "maintain.nx", source)
    shutil.copyfile(FIXTURES / "environment.json", environment)
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a - b\n")
    client = OpenProgram(OpenConfig(source, environment, tmp_path / "state.db", "maintain", tmp_path), provider=FixtureProvider.load(FIXTURES / "replies.json"))
    try:
        report = client.check()
        head = client.build(expected_revision=None, source_digest=report.source_digest)
        _, result, proposal = client.maintain(["calc.py"], "Fix add", expected_revision=head.revision, source_digest=report.source_digest)
        assert proposal and result.status == "accepted"
        grant = client.approve(proposal.digest, actor="fixture-user", confirmed=True)
        original = client.session.workspace._write_file

        def interrupted(root: int, before: SnapshotFile, change: FileChange, *, temporary: str, preserved: PreservedFile | None) -> None:
            original(root, before, change, temporary=temporary, preserved=preserved)
            raise SystemExit("after file write, before journal completion")

        monkeypatch.setattr(client.session.workspace, "_write_file", interrupted)
        with pytest.raises(SystemExit):
            client.apply(proposal.digest, grant.digest)
        recovered = OpenProgram(client.config, provider=FixtureProvider([]))
        try:
            assert recovered.recover(proposal.digest).state == "interrupted"
            with pytest.raises(ProgramError, match="apply_interrupted"):
                recovered.apply(proposal.digest, grant.digest)
            assert recovered.apply(proposal.digest, grant.digest, resume=True).state == "applied"
            assert "return a + b" in target.read_text()
        finally:
            recovered.close()
    finally:
        client.close()


@pytest.mark.oci
@pytest.mark.timeout(120)
def test_live_environment_drift_blocks_existing_grant_and_keeps_native_policy(tmp_path: Path) -> None:
    for name in ("maintain.nx", "environment.json"):
        shutil.copyfile(FIXTURES / name, tmp_path / name)
    target = tmp_path / "calc.py"
    original = "def add(a, b):\n    return a - b\n"
    target.write_text(original)
    provider = FixtureProvider.load(FIXTURES / "replies.json")
    config = OpenConfig(tmp_path / "maintain.nx", tmp_path / "environment.json", tmp_path / "state.db", "maintain", tmp_path)
    client = OpenProgram(config, provider=provider)
    try:
        digest = client.check().source_digest
        head = client.build(expected_revision=None, source_digest=digest)
        _, result, proposal = client.maintain(["calc.py"], "Fix add", expected_revision=head.revision, source_digest=digest)
        assert proposal and result.status == "accepted" and len(provider.requests) == 1
        grant = client.approve(proposal.digest, actor="review", confirmed=True)
        environment = json.loads(config.environment.read_text())
        environment["checks"][0]["cases"][0]["argv"] = ["python", "-c", "raise SystemExit(1)"]
        config.environment.write_text(json.dumps(environment))
        for operation in (
            lambda: client.inspect_proposal(proposal.digest),
            lambda: client.approve(proposal.digest, actor="review", confirmed=True),
            lambda: client.apply(proposal.digest, grant.digest),
        ):
            with pytest.raises(ProgramError, match="environment_changed"):
                operation()
            assert target.read_text() == original and len(provider.requests) == 1
        fresh = OpenProgram(config, provider=FixtureProvider([]))
        try:
            admission = fresh.inspect_proposal(proposal.digest)["admission"]
            assert not admission["accepted"]
            assert "checks.regression:checker_changed" in admission["reasons"]
            with pytest.raises(ProgramError, match="evidence_stale"):
                fresh.approve(proposal.digest, actor="review", confirmed=True)
            assert target.read_text() == original
        finally:
            fresh.close()
    finally:
        client.close()
