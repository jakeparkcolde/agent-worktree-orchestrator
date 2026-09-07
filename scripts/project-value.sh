#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

[ "$#" -eq 2 ] || die "usage: $0 <project-key> <field>"
PROJECT="$1"
FIELD="$2"
[ -f "$PROJECTS_FILE" ] || die "missing projects file: $PROJECTS_FILE"

python3 - "$PROJECTS_FILE" "$PROJECT" "$FIELD" <<'PY'
import sys, re
path, project, field = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
in_projects = False
in_target = False
for line in lines:
    if re.match(r"^projects:\s*$", line):
        in_projects = True
        continue
    if in_projects:
        m = re.match(r"^  ([A-Za-z0-9._-]+):\s*$", line)
        if m:
            in_target = m.group(1) == project
            continue
    if in_target:
        m = re.match(r"^    " + re.escape(field) + r":\s*(.*?)\s*$", line)
        if m:
            value = re.sub(r"\s+#.*$", "", m.group(1)).strip()
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            print(value)
            sys.exit(0)
sys.exit(2)
PY
