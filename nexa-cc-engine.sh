#!/usr/bin/env bash
# nexa-cc-engine — Engine launcher for Claude Code Nexa port (Unix)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export NEXA_JSON_EVENTS=1
export NEXA_PERMISSION_MODE="${1:-default}"
exec python -u src/main.py
