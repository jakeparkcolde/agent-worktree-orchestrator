#!/usr/bin/env python3
"""Find modules copied across registered projects.

`identical`: the same file content tracked in two or more projects.
`diverged`: the same parent-folder + file name (e.g. supabase/server.ts) with
different content in two or more projects — copies that were edited separately. Read-only; this is the
inventory step before choosing one home repository for a shared module.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from awo_report import project_list

EXTENSIONS = {'.py', '.ts', '.tsx', '.js', '.mjs', '.cjs', '.sh'}
GENERIC = {'__init__.py', 'index.ts', 'index.tsx', 'index.js', 'main.py', 'app.py', 'utils.py', 'util.py',
           'config.py', 'settings.py', 'conftest.py', 'setup.py', 'types.ts', 'utils.ts', 'constants.ts',
           'page.tsx', 'layout.tsx', 'route.ts', 'server.py', 'cli.py', 'common.sh', 'run.sh', 'test.sh'}
MIN_BYTES = 400
MANAGED = ('.claude/', '.moai/', '.codex/', '.agents/', '.orca/', 'node_modules/', 'vendor/', 'dist/', 'build/')


def tracked(repo):
    p = subprocess.run(['git', '-C', repo, 'ls-files', '-z'], capture_output=True, timeout=120)
    return [x for x in p.stdout.decode('utf-8', 'surrogateescape').split('\0') if x]


def scan(projects):
    by_hash, by_name = defaultdict(list), defaultdict(list)
    for name, repo in projects:
        for rel in tracked(repo):
            base = os.path.basename(rel)
            if Path(rel).suffix not in EXTENSIONS or base in GENERIC or any(('/' + m) in ('/' + rel) for m in MANAGED):
                continue
            path = Path(repo) / rel
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if len(data) < MIN_BYTES:
                continue
            item = dict(project=name, path=rel, lines=data.count(b'\n'), sha=hashlib.sha256(data).hexdigest())
            by_hash[item['sha']].append(item)
            parts = Path(rel).parts
            by_name['/'.join(parts[-2:]) if len(parts) > 1 else base].append(item)
    identical = []
    for items in by_hash.values():
        if len({i['project'] for i in items}) > 1:
            identical.append(dict(name='/'.join(Path(items[0]['path']).parts[-2:]), copies=items))
    same_hashes = {g['copies'][0]['sha'] for g in identical}
    diverged = []
    for base, items in by_name.items():
        projects_ = {i['project'] for i in items}
        hashes = {i['sha'] for i in items}
        if len(projects_) > 1 and len(hashes) > 1 and not hashes <= same_hashes:
            diverged.append(dict(name=base, copies=items))
    key = lambda g: (-len({c['project'] for c in g['copies']}), -max(c['lines'] for c in g['copies']))
    return dict(identical=sorted(identical, key=key), diverged=sorted(diverged, key=key))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--repo', action='append', default=[], metavar='NAME=PATH', help='also scan an unregistered repository')
    args = parser.parse_args()
    projects = [(n, str(Path(p).expanduser())) for n, p, _ in project_list() if Path(p).expanduser().is_dir()]
    for spec in args.repo:
        name, _, path = spec.partition('=')
        if not path or not Path(path).expanduser().is_dir():
            parser.error('--repo expects NAME=PATH of an existing directory')
        resolved = str(Path(path).expanduser().resolve())
        if resolved not in {str(Path(p).resolve()) for _, p in projects}:
            projects.append((name, resolved))
    res = scan(projects)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    for title, key in (('Identical copies (same content in several projects)', 'identical'),
                       ('Diverged copies (same name, different content)', 'diverged')):
        print(f'{title}: {len(res[key])}')
        for g in res[key][:args.limit]:
            print('  ' + g['name'])
            for c in g['copies']:
                print(f"    {c['project']}: {c['path']} ({c['lines']} lines, {c['sha'][:8]})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
