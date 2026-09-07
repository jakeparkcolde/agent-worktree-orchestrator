\
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/common.sh"

[ "$#" -ge 2 ] || die 'usage: task-start.sh <project> <task-name> [agent] [goal]'

project="$1"
task="$(safe_slug "$2")"
agent="${3:-}"
goal="${4:-}"

path="$("$SCRIPT_DIR/project-value.sh" "$project" path)" || die "missing project path"
base="$("$SCRIPT_DIR/project-value.sh" "$project" base_ref 2>/dev/null || echo origin/main)"
limit="$("$SCRIPT_DIR/project-value.sh" "$project" max_worktrees 2>/dev/null || echo 3)"
default_agent="$("$SCRIPT_DIR/project-value.sh" "$project" default_agent 2>/dev/null || echo codex)"
[ -n "$agent" ] || agent="$default_agent"

require_cmd git
require_cmd orca
require_cmd python3

[ -d "$path" ] || die "path not found: $path"
git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a Git repository"

if git_in_progress "$path"; then
  die "Git operation already in progress in primary checkout"
fi

git -C "$path" fetch --prune origin
git -C "$path" rev-parse --verify "$base" >/dev/null 2>&1 || die "base ref not found: $base"

count="$(git -C "$path" worktree list --porcelain | awk '/^worktree /{n++} END{print n+0}')"
if [ "$count" -ge "$limit" ]; then
  die "worktree limit reached ($count/$limit). Run: bin/awo cleanup $project"
fi

repo_id="$("$SCRIPT_DIR/orca-repo-id.sh" "$path")"
orca repo set-base-ref --repo "id:$repo_id" --ref "$base" --json >/dev/null

args=(orca worktree create --repo "id:$repo_id" --name "$task" --no-parent --agent "$agent" --json)
if [ -n "$goal" ]; then
  args+=(--prompt "$goal")
fi

"${args[@]}"
