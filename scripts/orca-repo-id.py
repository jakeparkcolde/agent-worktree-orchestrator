\
#!/usr/bin/env python3
import json, os, sys

if len(sys.argv) != 2:
    print("usage: orca-repo-id.py <absolute-repo-path>", file=sys.stderr)
    raise SystemExit(2)

target = os.path.realpath(sys.argv[1])
data = json.load(sys.stdin)

def walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)

for obj in walk(data):
    p = obj.get("path") or obj.get("repoPath") or obj.get("repo_path")
    rid = obj.get("id") or obj.get("repoId") or obj.get("repo_id")
    if p and rid:
        try:
            if os.path.realpath(os.path.expanduser(str(p))) == target:
                print(rid)
                raise SystemExit(0)
        except OSError:
            pass

raise SystemExit(1)
