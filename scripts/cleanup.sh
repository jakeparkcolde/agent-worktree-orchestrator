\
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/common.sh"

[ "$#" -ge 1 ] || die "usage: cleanup.sh <project> [--apply]"
project="$1"
mode="${2:-}"
apply=0
[ "$mode" = "--apply" ] && apply=1
[ -z "$mode" ] || [ "$mode" = "--apply" ] || die "unknown option: $mode"

path="$("$SCRIPT_DIR/project-value.sh" "$project" path)" || die "missing project path"
base="$("$SCRIPT_DIR/project-value.sh" "$project" base_ref 2>/dev/null || echo origin/main)"

require_cmd git
git -C "$path" fetch --prune origin
base_sha="$(git -C "$path" rev-parse "$base")" || die "base ref not found: $base"
primary="$(git -C "$path" rev-parse --show-toplevel)"

echo "cleanup mode: $([ "$apply" -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo "base: $base"
echo

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
git -C "$path" worktree list --porcelain >"$tmp"

wt=""
branch=""

check_one() {
  [ -n "$wt" ] || return 0

  if [ "$wt" = "$primary" ]; then
    echo "KEEP  $wt (primary)"
    wt=""; branch=""; return 0
  fi

  if [ ! -d "$wt" ]; then
    echo "PRUNE $wt (missing path)"
    wt=""; branch=""; return 0
  fi

  if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null || true)" ]; then
    echo "KEEP  $wt (dirty)"
    wt=""; branch=""; return 0
  fi

  head="$(git -C "$wt" rev-parse HEAD)"
  unique="$(git -C "$wt" rev-list --count "$base..HEAD")"

  if [ "$unique" -ne 0 ]; then
    echo "KEEP  $wt ($unique unique commit(s) vs $base)"
    wt=""; branch=""; return 0
  fi

  upstream="$(git -C "$wt" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [ -n "$upstream" ]; then
    unpushed="$(git -C "$wt" rev-list --count "$upstream..HEAD")"
    if [ "$unpushed" -ne 0 ]; then
      echo "KEEP  $wt ($unpushed unpushed commit(s))"
      wt=""; branch=""; return 0
    fi
  fi

  if ! git -C "$path" merge-base --is-ancestor "$head" "$base_sha"; then
    echo "KEEP  $wt (HEAD not contained in base)"
    wt=""; branch=""; return 0
  fi

  echo "SAFE  $wt${branch:+ [$branch]}"
  if [ "$apply" -eq 1 ]; then
    git -C "$path" worktree remove "$wt"
    if [ -n "$branch" ]; then
      if git -C "$path" branch -d "$branch" >/dev/null 2>&1; then
        echo "      removed worktree and merged local branch"
      else
        echo "      removed worktree; local branch preserved"
      fi
    fi
  fi

  wt=""; branch=""
}

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    worktree\ *)
      check_one
      wt="${line#worktree }"
      ;;
    branch\ refs/heads/*)
      branch="${line#branch refs/heads/}"
      ;;
    "")
      check_one
      ;;
  esac
done <"$tmp"
check_one

if [ "$apply" -eq 1 ]; then
  git -C "$path" worktree prune
fi
