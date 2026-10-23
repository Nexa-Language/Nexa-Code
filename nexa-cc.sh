#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec node "$APP_ROOT/ui-ink/dist/index.js" --cwd "$PWD" "$@"
