"""Compatibility launcher for the supported Ink interface."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    node = shutil.which("node")
    entry = Path(__file__).resolve().parents[1] / "ui-ink" / "dist" / "index.js"
    if node is None or not entry.is_file():
        raise SystemExit("Install Node 20+ and run pnpm --dir ui-ink install && pnpm --dir ui-ink build; see docs/INSTALL.md")
    os.execv(node, [node, str(entry), "--cwd", str(Path.cwd()), *sys.argv[1:]])


if __name__ == "__main__":
    main()
