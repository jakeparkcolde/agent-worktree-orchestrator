#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

echo "Agent Worktree Orchestrator doctor"
echo

fail=0
for cmd in git bash python3 awk sed; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "✓ $cmd: $(command -v "$cmd")"
  else
    echo "✗ $cmd not found"
    fail=1
  fi
done

for cmd in orca codex claude shellcheck; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "✓ $cmd: $(command -v "$cmd")"
  else
    echo "△ $cmd not found (optional depending on workflow)"
  fi
done

echo
if [ ! -f "$PROJECTS_FILE" ]; then
  echo "✗ projects.yaml not found"
  echo "  cp projects.example.yaml projects.yaml"
  fail=1
else
  echo "✓ projects file: $PROJECTS_FILE"
fi

exit "$fail"
