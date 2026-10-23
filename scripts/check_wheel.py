"""Install the engine wheel without dependency resolution and load its bundled .nx."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="nexa-code-wheel-") as directory:
        target = Path(directory) / "installed"
        subprocess.run(["uv", "pip", "install", "--no-deps", "--target", str(target), str(wheel)], check=True)
        program = """
import json, os
from pathlib import Path
import nexa_code
from nexa_code.commands import doctor
from nexa_code.fixture_provider import FixtureProvider
from nexa_code.session import Session
assert Path(nexa_code.__file__).is_relative_to(Path(os.environ['NEXA_WHEEL_TARGET']))
session = Session(Path.cwd(), provider=FixtureProvider([{'text':'wheel loaded'}]))
assert len(session.agent.tools) == 50
assert session.message('offline check').success
assert doctor(Path.cwd())['source_present']
print(json.dumps({'wheel_import': nexa_code.__file__, 'tools': len(session.agent.tools), 'result': session.state.output}))
session.close()
"""
        subprocess.run(
            [sys.executable, "-c", program],
            cwd=directory,
            check=True,
            env={**os.environ, "PYTHONPATH": str(target), "NEXA_WHEEL_TARGET": str(target), "NEXA_QUIET": "1"},
        )


if __name__ == "__main__":
    main()
