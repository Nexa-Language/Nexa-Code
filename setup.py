"""Include authoritative Nexa definitions in standalone engine wheels."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildDefinitions(build_py):
    def run(self) -> None:
        super().run()
        source = Path(__file__).parent / "src"
        target = Path(self.build_lib) / "nexa_code" / "definitions"
        for path in source.rglob("*.nx"):
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


setup(cmdclass={"build_py": BuildDefinitions})
