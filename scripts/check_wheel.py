"""Install Code and released runtime wheels outside every editable checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RUNTIME_SHA = "274379606e53c90d2d25774f6bb8984c777d0759"
SMOKE = """
import importlib.metadata, json, os
from pathlib import Path
import nexa_code
import src.open_programs.compiler
from nexa_code.fixture_provider import FixtureProvider
from nexa_code.open_program import OpenConfig, OpenProgram
from nexa_code.session import Session
root = Path(os.environ["NEXA_WHEEL_ENV"])
assert Path(nexa_code.__file__).is_relative_to(root)
assert Path(src.open_programs.compiler.__file__).is_relative_to(root)
assert importlib.metadata.version("nexa-lang") == "3.0.0"
assert importlib.metadata.version("nexa-code") == "3.0.0.dev0"
session = Session(Path.cwd(), provider=FixtureProvider([{"text": "wheel loaded"}]))
assert len(session.agent.tools) == 50
assert session.message("offline check").success
session.close()
source, environment = Path("demo.nx"), Path("environment.json")
source.write_text('language "3.0" program Demo { goal answer() -> Int { stage runtime intent "Return 42" implementation value 42 } }')
environment.write_text(json.dumps({"image":"python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"}))
program = OpenProgram(OpenConfig(source.resolve(), environment.resolve(), Path("native.db").resolve(), "demo", Path.cwd()))
report = program.check()
assert report.ok
head = program.build(expected_revision=None, source_digest=report.source_digest)
assert program.build(expected_revision=head.revision, source_digest=report.source_digest, locked=True) == head
program.close()
print(json.dumps({"engine_import": nexa_code.__file__, "runtime_import": src.open_programs.compiler.__file__, "legacy_tools":50,"native_revision":head.revision}))
"""


def validate_metadata(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(name).decode()
    assert "Version: 3.0.0.dev0" in metadata
    assert "git+https://github.com/Nexa-Language/Nexa.git@" + RUNTIME_SHA in metadata
    assert "file://" not in metadata


def verify(wheel: Path, runtime: Path, target: Path) -> None:
    validate_metadata(wheel)
    subprocess.run(["uv", "venv", "--python", sys.executable, str(target)], check=True)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(runtime), "httpx>=0.28,<1"], check=True)
    subprocess.run(["uv", "pip", "install", "--no-deps", "--python", str(python), str(wheel)], check=True)
    workspace = target / "smoke-workspace"
    workspace.mkdir()
    environment = {**os.environ, "NEXA_WHEEL_ENV": str(target), "NEXA_QUIET": "1"}
    environment.pop("PYTHONPATH", None)
    subprocess.run([str(python), "-I", "-c", SMOKE], cwd=workspace, check=True, env=environment)
    print(
        json.dumps(
            {
                "python": str(python),
                "wheel": str(wheel),
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "runtime_wheel": str(runtime),
                "runtime_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--runtime-wheel", type=Path, required=True)
    parser.add_argument("--keep", type=Path, help="Keep a new isolated environment for downstream package verification")
    args = parser.parse_args()
    if args.keep:
        if args.keep.exists():
            parser.error("--keep must name a new directory")
        verify(args.wheel.resolve(), args.runtime_wheel.resolve(), args.keep.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="nexa-code-wheel-") as directory:
            verify(args.wheel.resolve(), args.runtime_wheel.resolve(), Path(directory) / "environment")


if __name__ == "__main__":
    main()
