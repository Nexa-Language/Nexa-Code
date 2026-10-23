#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Legacy positional mode remains an alias; workspace defaults to the caller's cwd.
if [[ "${1:-}" =~ ^(default|plan|auto|bypass)$ ]]; then
  mode="$1"; shift
  set -- --mode "$mode" "$@"
fi
exec uv run --project "$APP_ROOT" --no-sync nexa-code-engine "$@"
