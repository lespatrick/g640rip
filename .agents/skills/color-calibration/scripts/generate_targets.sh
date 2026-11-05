#!/usr/bin/env bash
set -e

# ArgyllCMS Target Generator for Canon G640
# Delegates to repo-level scripts/generate_targets.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_SCRIPT="$(cd "$SCRIPT_DIR/../../../../scripts" && pwd)/generate_targets.sh"

if [ -f "$ROOT_SCRIPT" ]; then
    exec "$ROOT_SCRIPT" "$@"
else
    echo >&2 "[ERROR] Root script not found at $ROOT_SCRIPT"
    exit 1
fi
