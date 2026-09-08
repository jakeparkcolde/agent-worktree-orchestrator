#!/usr/bin/env python3
"""Conservative worktree discovery and cleanup. No file contents are inspected."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

SCRIPT = Path(__file__).resolve().parent


def run(argv, ok=(0,)):
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    if p.returncode not in ok:
        raise RuntimeError('command failed: ' + ' '.join(argv[:3]))
    return p.stdout.decode('utf-8', 'surrogateescape').rstrip('\n')


def git(path, *args, ok=(0,)):
    return run(['git', '-C', str(path), *args], ok)


def config(project, field, default=None):
    try:
        return run([str(SCRIPT / 'project-value.sh'), project, field])
    except RuntimeError:
        if default is None:
            raise
        return default


def category(name):
    parts = set(Path(name.lower()).parts)
    if parts & {'runtime', '.runtime', 'logs', 'log', 'sessions', '.sessions', '.orca'} or name.lower().endswith(('.log', '.pid', '.sqlite', '.sqlite3', '.db', '.jsonl')):
        return 'runtime'
    if parts & {'artifacts', 'artifact', 'outputs', 'archive', 'archives', 'reports', 'exports', 'backups'} or name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.pdf', '.zip', '.tar', '.gz', '.mp4', '.mp3', '.wav', '.docx', '.xlsx', '.pptx')):
        return 'artifacts'
    if parts & {'tmp', 'temp', 'scratch', '.scratch', '.cache', 'cache'}:
        return 'scratch'
    return 'source'


def records(path):
    result = []
    # -z avoids Git's quoting and newline ambiguities in filenames.
    for block in git(path, 'worktree', 'list', '--porcelain', '-z').split('\0\0'):
        row = {}
        for line in block.split('\0'):
            key, _, value = line.partition(' ')
            row[key] = value
        if 'worktree' in row:
            row['worktree'] = str(Path(row['worktree']).resolve())
            result.append(row)
    return result


def save(state_path, state):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=state_path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2)
        os.replace(name, state_path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inspect(path, base, record, primary, meta, now, thresholds):
    row = {'path': path, 'branch': record.get('branch', ''), 'classification': 'BLOCKED', 'reasons': [], 'metadata': meta}
    try:
        if path == primary:
            row['reasons'] = ['primary checkout']
            return row
        if 'locked' in record or 'prunable' in record or not Path(path).is_dir():
            row['reasons'] = ['locked, missing, or prunable worktree']
            return row
        head = git(path, 'rev-parse', 'HEAD')
        git_identity = Path(git(path, 'rev-parse', '--absolute-git-dir')).stat()
        link_stat = (Path(path) / '.git').stat()
        identity = [git_identity.st_dev, git_identity.st_ino, getattr(git_identity, 'st_birthtime', 0), link_stat.st_ino, link_stat.st_mtime_ns, link_stat.st_ctime_ns]
        if meta.get('gitdir_identity') != identity:
            meta.update(first_seen_at=now, last_activity_at=now, gitdir_identity=identity)
        status = git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignored=matching')
        gitdir = Path(git(path, 'rev-parse', '--absolute-git-dir'))
        in_progress = any((gitdir / n).exists() for n in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'BISECT_LOG'))
        tracked = git(path, 'ls-files', '-z').split('\0')
        flags = git(path, 'ls-files', '-v', '-z').split('\0')
        hidden = any(item and (item[0].islower() or item[0] == 'S') for item in flags)
        kinds = {k: sum(category(n) == k for n in tracked if n) for k in ('runtime', 'artifacts', 'scratch', 'source')}
        topology = int(git(path, 'rev-list', '--count', base + '..HEAD'))
        cherry = git(path, 'cherry', base, 'HEAD').splitlines()
        patch_unique = sum(x.startswith('+') for x in cherry)
        equivalent = sum(x.startswith('-') for x in cherry)
        diff = git(path, 'diff', '--no-ext-diff', '--no-textconv', '--name-only', '-z', base, 'HEAD')
        tree_count = len([n for n in diff.split('\0') if n])
        ancestor = subprocess.run(['git', '-C', path, 'merge-base', '--is-ancestor', head, base], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        upstream = git(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}', ok=(0, 128))
        unpushed = int(git(path, 'rev-list', '--count', upstream + '..HEAD')) if upstream else None
        fingerprint = hashlib.sha256((head + '\0' + status).encode('utf-8', 'surrogateescape')).hexdigest()
        activity = float(meta.get('last_activity_at', now))
        evidence = max((f.stat().st_mtime for f in (gitdir / 'HEAD', gitdir / 'index', gitdir / 'logs' / 'HEAD') if f.exists()), default=0)
        activity = max(activity, evidence)
        if meta.get('fingerprint') != fingerprint:
            activity = now
        meta.update(last_activity_at=activity, last_seen_at=now, fingerprint=fingerprint, branch=row['branch'], base_ref=base)
        age = max(0, now - float(meta['first_seen_at'])) / 3600
        idle = max(0, now - activity) / 3600
        row.update(head=head, topology_unique=topology, patch_unique=patch_unique, patch_equivalent=equivalent, tree_diff_files=tree_count, head_contained=ancestor, unpushed=unpushed, tracked_categories=kinds, age_hours=age, idle_hours=idle)
        reasons = row['reasons']
        if hidden or status or in_progress or (unpushed is not None and unpushed > 0):
            reasons.append('hidden index flags, dirty/ignored/untracked data, in-progress Git operation, or unpushed commits')
        elif kinds['runtime'] or kinds['artifacts'] or kinds['scratch']:
            row['classification'] = 'ARCHIVE' if kinds['artifacts'] and not kinds['runtime'] else 'REVIEW'
            reasons.append('tracked runtime/artifacts/scratch require manual preservation review')
        elif age < thresholds[0] or idle < thresholds[0]:
            row['classification'] = 'ACTIVE'
        elif age < thresholds[1] or idle < thresholds[1]:
            row['classification'] = 'ACTIVE_IDLE'
        elif patch_unique == 0 and tree_count == 0 and ancestor:
            row['classification'] = 'SAFE_CLEANUP'
        elif patch_unique == 0 and tree_count == 0:
            row['classification'] = 'SYNCED'
            reasons.append('equivalent content, but HEAD is not contained in base; manual review')
        elif idle >= thresholds[2]:
            row['classification'] = 'STALE'
        elif patch_unique or tree_count:
            row['classification'] = 'MERGE'
        else:
            row['classification'] = 'REVIEW'
        if not upstream and not ancestor:
            row['classification'] = 'BLOCKED'
            reasons.append('no upstream and HEAD is not contained in base')
    except (RuntimeError, ValueError, OSError, KeyError):
        row['classification'] = 'BLOCKED'
        row['reasons'] = ['inspection failed; no cleanup permitted']
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['audit', 'watch', 'cleanup'])
    parser.add_argument('project')
    parser.add_argument('--json', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--worktree')
    group.add_argument('--all-safe', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--sessions', action='store_true')
    parser.add_argument('--notify', action='store_true')
    args = parser.parse_args()
    if (args.sessions or args.notify) and args.command != 'watch':
        parser.error('--sessions and --notify are watch options')
    if args.apply and (args.command != 'cleanup' or not (args.worktree or args.all_safe)):
        parser.error('--apply requires cleanup and explicit --worktree PATH or --all-safe')
    path = str(Path(config(args.project, 'path')).expanduser().resolve())
    base = config(args.project, 'base_ref', 'origin/main')
    thresholds = tuple(float(config(args.project, k, str(v))) for k, v in [('active_hours', 24), ('recent_hours', 72), ('stale_hours', 168)])
    limit = int(config(args.project, 'max_worktrees', '3'))
    if limit < 1 or not all(math.isfinite(v) for v in thresholds):
        raise RuntimeError('invalid thresholds or max_worktrees')
    if not (24 <= thresholds[0] <= thresholds[1] and 72 <= thresholds[1] <= thresholds[2]):
        raise RuntimeError('thresholds must be ordered and preserve minimum 24h/72h protection')
    if args.apply:
        git(path, 'fetch', '--prune', 'origin')
    git(path, 'rev-parse', '--verify', base + '^{commit}')
    worktrees = records(path)
    if not worktrees:
        raise RuntimeError('no registered worktrees')
    primary = worktrees[0]['worktree']
    common = Path(git(path, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = Path(path) / common
    state_path = common.resolve() / 'awo' / 'worktrees.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not isinstance(state, dict):
        raise RuntimeError('invalid metadata')
    now = time.time()
    for value in state.values():
        if not isinstance(value, dict) or any(not isinstance(value.get(k), (int, float)) or not math.isfinite(value[k]) or value[k] > now or value[k] < 0 for k in ('first_seen_at', 'last_activity_at')):
            raise RuntimeError('invalid or future-dated metadata; refusing cleanup')
    rows = []
    for record in worktrees:
        wt = record['worktree']
        meta = state.setdefault(wt, {'project': args.project, 'path': wt, 'created_at': None, 'first_seen_at': now, 'last_activity_at': now, 'source': 'orca-inferred' if 'orca' in Path(wt).parts or '.orca' in Path(wt).parts else 'git-discovery', 'agent': None})
        rows.append(inspect(wt, base, record, primary, meta, now, thresholds))
    save(state_path, state)
    selected = rows
    if args.worktree:
        target = str(Path(args.worktree).expanduser().resolve())
        selected = [r for r in rows if r['path'] == target]
        if not selected:
            raise RuntimeError('--worktree must identify a registered exact path')
    failed = False
    if args.apply:
        for row in selected:
            if row['classification'] != 'SAFE_CLEANUP':
                failed = failed or bool(args.worktree)
                continue
            current = {r['worktree']: r for r in records(path)}
            fresh = inspect(row['path'], base, current.get(row['path'], {'prunable': ''}), primary, state[row['path']], time.time(), thresholds)
            if fresh['classification'] != 'SAFE_CLEANUP' or fresh.get('head') != row.get('head'):
                row['reasons'].append('revalidation refused cleanup')
                failed = True
                continue
            git(path, 'worktree', 'remove', '--', row['path'])
            row['removed'] = True
    alerts = []
    if len(rows) >= limit:
        alerts.append('max-worktrees threshold reached: %s/%s' % (len(rows), limit))
    for row in rows:
        if row.get('idle_hours', 0) >= thresholds[2]:
            alerts.append('ACTION_REQUIRED (168h threshold): ' + row['path'])
        elif row.get('age_hours', 0) >= thresholds[1]:
            alerts.append('STALE (72h threshold): ' + row['path'])
        elif row.get('age_hours', 0) >= thresholds[0]:
            alerts.append('NOTICE (24h threshold): ' + row['path'])
    report = {'project': args.project, 'base_ref': base, 'mode': 'APPLY' if args.apply else 'DRY-RUN', 'worktrees': selected, 'alerts': alerts}
    if args.sessions:
        from awo_sessions import inspect_sessions
        report['sessions'] = inspect_sessions()
    if args.notify and alerts:
        if sys.platform != 'darwin':
            raise RuntimeError('notifications require macOS')
        subprocess.run(['osascript', '-e', 'on run argv\ndisplay notification (item 1 of argv) with title \"AWO watch\"\nend run', str(len(alerts)) + ' worktree alerts; run awo watch for details'], check=True)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print('%s %s (base %s)' % (args.command, report['mode'], base))
        for row in selected:
            print('%-13s %s topology=%s patch-unique=%s equivalent=%s tree-files=%s%s' % (row['classification'], row['path'], row.get('topology_unique', '?'), row.get('patch_unique', '?'), row.get('patch_equivalent', '?'), row.get('tree_diff_files', '?'), ' REMOVED' if row.get('removed') else ''))
            for reason in row['reasons']:
                print('  ' + reason)
        for session in report.get('sessions', []):
            print('SESSION %s pid=%s elapsed=%ss%s' % (session['executable'], session['pid'], session['elapsed_seconds'], ' STALE' if session['stale'] else ''))
        if args.command == 'watch':
            for alert in alerts:
                print('ALERT ' + alert)
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, TypeError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
