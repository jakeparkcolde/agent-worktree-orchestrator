\
#!/usr/bin/env bash
set -u

AWO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECTS_FILE="${AWO_PROJECTS_FILE:-${AWO_ROOT}/projects.yaml}"

die() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }
info() { echo "INFO: $*"; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

safe_slug() {
  printf "%s" "$1" |
    tr '[:upper:]' '[:lower:]' |
    sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

git_in_progress() {
  local repo="$1"
  local common_dir gitdir

  common_dir="$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null)" || return 1
  gitdir="$(git -C "$repo" rev-parse --git-dir 2>/dev/null)" || return 1

  case "$common_dir" in /*) ;; *) common_dir="$repo/$common_dir" ;; esac
  case "$gitdir" in /*) ;; *) gitdir="$repo/$gitdir" ;; esac

  [ -d "$gitdir/rebase-merge" ] ||
  [ -d "$gitdir/rebase-apply" ] ||
  [ -f "$gitdir/MERGE_HEAD" ] ||
  [ -f "$gitdir/CHERRY_PICK_HEAD" ] ||
  [ -f "$gitdir/REVERT_HEAD" ] ||
  [ -f "$common_dir/MERGE_HEAD" ]
}
