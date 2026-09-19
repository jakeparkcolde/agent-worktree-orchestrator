#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"
[ "$#" -eq 2 ] || die 'usage: prepare-base.sh <repo-path> <base-ref>'
repo="$1"
base="$2"
if git -C "$repo" remote get-url origin >/dev/null 2>&1; then
  git -C "$repo" fetch --prune origin
elif [ -n "$(git -C "$repo" remote)" ]; then
  die 'origin is missing; configure the intended remote before starting'
else
  # Explicit local base only. An unavailable remote is never treated as offline success.
  local_ref="$base"
  case "$base" in refs/heads/*) ;; *) local_ref="refs/heads/$base" ;; esac
  git -C "$repo" show-ref --verify --quiet "$local_ref" || die 'local-only repository requires a local branch base_ref'
  warn "local-only repository: using $local_ref without fetching"
fi
git -C "$repo" rev-parse --verify "$base^{commit}" >/dev/null
