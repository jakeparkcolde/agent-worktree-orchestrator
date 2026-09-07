\
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

out="$("$ROOT/bin/awo" help)"
printf "%s" "$out" | grep -q "Agent Worktree Orchestrator"
printf "%s" "$out" | grep -q "awo cleanup"
echo "test_cli: ok"
