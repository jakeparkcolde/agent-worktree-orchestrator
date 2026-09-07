\
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

cat >"$tmp" <<'YAML'
projects:
  demo:
    path: "/tmp/demo"
    base_ref: "origin/main"
    max_worktrees: 3
YAML

export AWO_PROJECTS_FILE="$tmp"
[ "$("$ROOT/scripts/project-value.sh" demo path)" = "/tmp/demo" ]
[ "$("$ROOT/scripts/project-value.sh" demo base_ref)" = "origin/main" ]
[ "$("$ROOT/scripts/project-value.sh" demo max_worktrees)" = "3" ]
echo "test_project_value: ok"
