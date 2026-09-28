#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

out="$("$ROOT/bin/awo" help)"
printf "%s" "$out" | grep -q "Agent Worktree Orchestrator"
printf "%s" "$out" | grep -q "awo cleanup"
printf "%s" "$out" | grep -q "awo terminals"
printf "%s" "$out" | grep -q "awo jev-trial"
# Execute without Bash's fallback for files missing a valid shebang.
python3 - "$ROOT" <<'PYTHON'
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1])
result = subprocess.run([str(root / "bin/awo"), "help"],
                        check=True, capture_output=True, text=True)
assert "awo cleanup" in result.stdout
assert "--details" in result.stdout
result = subprocess.run([str(root / "bin/awo"), "board", "--help"],
                        check=True, capture_output=True, text=True)
assert "--details" in result.stdout and "--json" in result.stdout
assert "--include-done" in result.stdout
result = subprocess.run([str(root / "bin/awo"), "task", "plan", "--help"],
                        check=True, capture_output=True, text=True)
assert "--date" in result.stdout and "--clear-date" in result.stdout
result = subprocess.run([str(root / "bin/awo"), "task", "suggest", "--help"],
                        check=True, capture_output=True, text=True)
assert "--intent" in result.stdout and "--request-id" in result.stdout
result = subprocess.run([str(root / "scripts/orca-repo-id.py"), str(root)],
                        input=json.dumps({"path": str(root), "id": "demo-id"}),
                        check=True, capture_output=True, text=True)
assert result.stdout.strip() == "demo-id"
PYTHON
echo "test_cli: ok"
