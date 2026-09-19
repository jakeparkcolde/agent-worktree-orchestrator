#!/usr/bin/env python3
"""Cross-project work report: uncommitted files with their owner session,
unpushed commits, branches behind base, and agents sharing one checkout.

Read-only. Owners come from the work ledger (awo_ledger); files changed by
shell commands or before the ledger existed show as unknown owner.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import awo_ledger as ledger
from awo_audit import category, records

ROOT = Path(__file__).resolve().parent.parent


def projects_file():
    return Path(os.environ.get('AWO_PROJECTS_FILE') or ROOT / 'projects.yaml')


def project_list(path=None):
    """[(name, path, base_ref)] from projects.yaml (same minimal format as project-value.sh)."""
    out, current, inside = [], None, False
    for line in Path(path or projects_file()).read_text(encoding='utf-8').splitlines():
        if re.match(r'^projects:\s*$', line):
            inside = True
            continue
        if not inside:
            continue
        m = re.match(r'^  ([A-Za-z0-9._-]+):\s*$', line)
        if m:
            current = {'name': m.group(1), 'path': None, 'base_ref': 'origin/main'}
            out.append(current)
            continue
        m = re.match(r'^    (path|base_ref):\s*(.*?)\s*$', line)
        if m and current is not None:
            value = re.sub(r'\s+#.*$', '', m.group(2)).strip().strip('"').strip("'")
            current[m.group(1)] = value
    return [(p['name'], p['path'], p['base_ref']) for p in out if p['path']]


def git(path, *args):
    p = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True,
                       env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}, timeout=60)
    return p.stdout.strip() if p.returncode == 0 else None


def dirty_entries(path):
    raw = subprocess.run(['git', '-C', str(path), 'status', '--porcelain=v1', '-z'], capture_output=True,
                         env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}, timeout=60).stdout.decode('utf-8', 'surrogateescape')
    parts, out, i = raw.split('\0'), [], 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if len(item) < 4:
            continue
        out.append((item[:2], item[3:]))
        if item[0] in 'RC':
            i += 1  # skip the original path of a rename/copy
    return out


def checkout_state(path, base, owner_map, alive):
    path = str(Path(path).resolve())
    entries = dirty_entries(path)
    repo_owners = {rel: row for (repo, rel), row in owner_map.items() if repo == path}
    groups = {}
    for code, rel in entries:
        row = repo_owners.get(rel)
        if row is None and rel.endswith('/'):
            inside = [r for k, r in repo_owners.items() if k.startswith(rel)]
            row = max(inside, key=lambda r: r.get('ts') or 0) if inside else None
        key = row.get('session') if row else ('__runtime__' if category(rel.rstrip('/')) == 'runtime' else None)
        g = groups.setdefault(key, dict(session=key, agent=row.get('agent') if row else None,
                                        terminal=row.get('terminal') if row else None,
                                        alive=bool(row and row.get('terminal') in alive), files=[], last_ts=0))
        g['files'].append(rel)
        if row and (row.get('ts') or 0) > g['last_ts']:
            g['last_ts'] = row.get('ts') or 0
    for g in groups.values():
        g['files'].sort()
    owners = sorted(groups.values(), key=lambda g: (g['session'] in (None, '__runtime__'), g['session'] == '__runtime__', -len(g['files'])))
    upstream = git(path, 'rev-parse', '--abbrev-ref', '@{u}')
    unpushed = int(git(path, 'rev-list', '--count', '@{u}..HEAD') or 0) if upstream else None
    counts = git(path, 'rev-list', '--left-right', '--count', base + '...HEAD')
    behind, ahead = (int(x) for x in counts.split()) if counts else (None, None)
    return dict(path=path, branch=git(path, 'rev-parse', '--abbrev-ref', 'HEAD'), dirty=len(entries),
                owners=owners, upstream=upstream, unpushed=unpushed, behind=behind, ahead=ahead)


def needs_attention(c):
    return bool(c['dirty'] or c.get('unpushed') or (c.get('behind') or 0) > 20)


def render_markdown(rep):
    lines = [f"# AWO 작업 장부 보고 · {rep['generated']}", '']
    busy = [c for c in rep['checkouts'] if needs_attention(c)]
    total_dirty = sum(c['dirty'] for c in rep['checkouts'])
    unknown = sum(len(g['files']) for c in rep['checkouts'] for g in c['owners'] if g['session'] is None)
    lines.append(f"- 폴더 {len(rep['checkouts'])}곳 중 손볼 곳 {len(busy)}곳 · 커밋 안 된 항목 {total_dirty}개(주인 모름 {unknown}개)")
    if rep['warnings']:
        lines += ['', '## ⚠️ 동시 작업 경고 (커밋이 섞일 수 있음)'] + ['- ' + w for w in rep['warnings']]
    for c in busy:
        where = c['path'].replace(str(Path.home()), '~')
        lines += ['', f"### {c['project']} · {where} ({c['branch']})"]
        if c.get('unpushed'):
            lines.append(f"- GitHub에 안 올린 커밋 {c['unpushed']}개")
        if (c.get('behind') or 0) > 20:
            lines.append(f"- 기본 브랜치보다 {c['behind']}커밋 뒤처짐")
        for g in c['owners']:
            shown = ', '.join(g['files'][:5]) + (f" 외 {len(g['files']) - 5}개" if len(g['files']) > 5 else '')
            if g['session'] is None:
                lines.append(f"- 주인 모름 {len(g['files'])}개: {shown}")
            elif g['session'] == '__runtime__':
                lines.append(f"- 자동 기록 파일 {len(g['files'])}개 (무시 목록 후보): {shown}")
            else:
                state = '창 살아 있음' if g['alive'] else '창 닫힘/모름'
                when = datetime.fromtimestamp(g['last_ts']).strftime('%m-%d %H:%M') if g['last_ts'] else '?'
                lines.append(f"- {g['agent']} 세션 `{str(g['session'])[:8]}` ({state}, 마지막 {when}) {len(g['files'])}개: {shown}")
    clean = len(rep['checkouts']) - len(busy)
    if clean:
        lines += ['', f'정리할 것 없음: {clean}곳']
    for e in rep['errors']:
        lines.append('- 확인 실패: ' + e)
    return '\n'.join(lines) + '\n'


def orca_terminals():
    try:
        p = subprocess.run(['orca', 'terminal', 'list', '--json'], capture_output=True, text=True, timeout=40)
        value = json.loads(p.stdout)
        return value.get('result', value)
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None


def build(ingest=True):
    errors, checkouts = [], []
    if ingest:
        try:
            ledger.ingest_codex(days=3)
        except OSError as exc:
            errors.append('codex ingest: ' + str(exc))
    owner_map = ledger.owners()
    listing = orca_terminals()
    alive = set()
    if isinstance(listing, dict):
        alive = {t.get('handle') for t in listing.get('terminals', []) if isinstance(t, dict) and t.get('agentIdentity') and t.get('connected')}
    else:
        errors.append('Orca terminal list unavailable; owner liveness unknown')
    paths = set()
    for name, primary, base in project_list():
        try:
            worktrees = records(Path(primary).expanduser())
        except (RuntimeError, OSError):
            errors.append(f'{name}: not a readable git checkout')
            continue
        for row in worktrees:
            if not Path(row['worktree']).is_dir():
                continue
            paths.add(row['worktree'])
            try:
                checkouts.append(dict(checkout_state(row['worktree'], base, owner_map, alive), project=name))
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{row['worktree']}: {exc}")
    warnings = []
    if isinstance(listing, dict):
        from awo_terminals import inventory
        warnings = inventory(paths, listing, int(time.time() * 1000), 12, os.environ.get('ORCA_TERMINAL_HANDLE'))['warnings']
    return dict(generated=datetime.now().strftime('%Y-%m-%d %H:%M'), checkouts=checkouts, warnings=warnings, errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--save', action='store_true', help='also write ~/.awo/reports/YYYY-MM-DD.md')
    parser.add_argument('--notify', action='store_true', help='macOS notification with the summary')
    parser.add_argument('--no-ingest', action='store_true', help='skip reading new Codex sessions')
    args = parser.parse_args()
    rep = build(ingest=not args.no_ingest)
    text = render_markdown(rep)
    if args.save:
        out = Path(os.environ.get('AWO_REPORT_DIR') or Path.home() / '.awo' / 'reports') / (datetime.now().strftime('%Y-%m-%d') + '.md')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        rep['saved'] = str(out)
    if args.notify and sys.platform == 'darwin':
        busy = sum(1 for c in rep['checkouts'] if needs_attention(c))
        msg = f"손볼 폴더 {busy}곳 · 동시작업 경고 {len(rep['warnings'])}건"
        subprocess.run(['osascript', '-e', 'on run argv\ndisplay notification (item 1 of argv) with title "AWO 작업 장부"\nend run', msg], check=False)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if args.json else text + (f"\nsaved: {rep['saved']}" if rep.get('saved') else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
