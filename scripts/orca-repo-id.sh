#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

[ "$#" -eq 1 ] || die "usage: $0 <repo-path>"
repo="$1"
require_cmd orca
require_cmd python3

json="$(orca repo list --json)"
if rid="$(printf "%s" "$json" | "$SCRIPT_DIR/orca-repo-id.py" "$repo" 2>/dev/null)"; then
  printf "%s\n" "$rid"
  exit 0
fi

orca repo add --path "$repo" --json >/dev/null
json="$(orca repo list --json)"
printf "%s" "$json" | "$SCRIPT_DIR/orca-repo-id.py" "$repo" ||
  die "repo was added to Orca but its id could not be resolved"
