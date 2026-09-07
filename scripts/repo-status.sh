#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

[ "$#" -eq 1 ] || die "usage: $0 <project-key>"
project="$1"

path="$("$SCRIPT_DIR/project-value.sh" "$project" path)" || die "missing $project.path"
base="$("$SCRIPT_DIR/project-value.sh" "$project" base_ref 2>/dev/null || echo origin/main)"
limit="$("$SCRIPT_DIR/project-value.sh" "$project" max_worktrees 2>/dev/null || echo 3)"

[ -d "$path" ] || die "path not found: $path"
git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a Git repository: $path"

git -C "$path" fetch --prune origin

echo "project: $project"
echo "path: $path"
echo "base_ref: $base"
echo "max_worktrees: $limit"
echo

if git_in_progress "$path"; then
  echo "WARNING: Git operation in progress"
fi

echo "primary status:"
git -C "$path" status --short --branch
echo
echo "worktrees:"
git -C "$path" worktree list

count="$(git -C "$path" worktree list --porcelain | awk '/^worktree /{n++} END{print n+0}')"
echo
echo "worktree_count: $count / $limit"

if git -C "$path" rev-parse --verify "$base" >/dev/null 2>&1; then
  echo "base_sha: $(git -C "$path" rev-parse --short "$base")"
else
  echo "WARNING: base ref not found: $base"
fi
