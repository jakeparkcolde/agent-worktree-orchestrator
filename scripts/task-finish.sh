#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

repo="${1:-$PWD}"
git -C "$repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "not a Git repository: $repo"

if git_in_progress "$repo"; then
  die "Git operation in progress"
fi

branch="$(git -C "$repo" branch --show-current)"
[ -n "$branch" ] || die "detached HEAD"

if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo "NOT READY: uncommitted changes"
  git -C "$repo" status --short
  exit 2
fi

git -C "$repo" fetch --prune origin
base="$(git -C "$repo" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"
[ -n "$base" ] || base="origin/main"
git -C "$repo" rev-parse --verify "$base" >/dev/null 2>&1 || die "base ref not found: $base"

read -r behind ahead <<EOF
$(git -C "$repo" rev-list --left-right --count "$base...HEAD")
EOF

echo "branch: $branch"
echo "base: $base"
echo "base_commits_not_in_feature: $behind"
echo "feature_unique_commits: $ahead"

changed="$(git -C "$repo" diff --name-only "$base...HEAD")"
echo
echo "changed files:"
printf "%s\n" "${changed:-<none>}"

risk="$(printf "%s\n" "$changed" | grep -Ei '(^|/)(migrations?|schema|prisma|auth|payment|billing|permissions?|secrets?|terraform|infra|deploy|production)(/|\.|$)' || true)"
if [ -n "$risk" ]; then
  echo
  echo "HIGH-RISK candidates:"
  printf "%s\n" "$risk"
  echo "Human approval required before merge."
fi

upstream="$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
if [ -n "$upstream" ]; then
  unpushed="$(git -C "$repo" rev-list --count "$upstream..HEAD")"
  echo
  echo "upstream: $upstream"
  echo "unpushed_commits: $unpushed"
else
  echo
  echo "upstream: <none>"
fi

if [ "$behind" -gt 0 ]; then
  echo
  echo "ACTION: synchronize with $base and re-run validation before merge."
fi
