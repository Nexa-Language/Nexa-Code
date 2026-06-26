#!/usr/bin/env bash
# nexa-cc — CLI wrapper for Claude Code Nexa port
# Usage: nexa-cc [args passed to nexa run]
# Install: ln -s $(pwd)/nexa-cc.sh /usr/local/bin/nexa-cc  (or add to PATH)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec nexa run src/main.nx "$@"
