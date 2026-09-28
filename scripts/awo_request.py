#!/usr/bin/env python3
"""Resolve a request, inspect worktrees, and reuse or start one concrete goal."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

from awo_audit import git, records, save

ROOT = Path(__file__).resolve().parents[1]


def normalize(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def registry():
    """Keep the existing scalar registry format; aliases are pipe-separated."""
    source = Path(os.environ.get('AWO_PROJECTS_FILE', ROOT / 'projects.yaml'))
    keys = re.findall(r'^  ([A-Za-z0-9._-]+):\s*$', source.read_text(), re.M)
    result = {}
    for key in keys:
        fields = {}
        for field, default in [('path', None), ('aliases', ''), ('description', ''), ('base_ref', 'origin/main'),
                               ('max_worktrees', '3')]:
            p = subprocess.run([str(ROOT / 'scripts/project-value.sh'), key, field],
                               capture_output=True, text=True)
            if p.returncode and (p.returncode != 2 or default is None):
                raise RuntimeError(f'cannot read {key}.{field}: {p.stderr.strip()}')
            fields[field] = default if p.returncode else p.stdout.strip()
        result[key] = fields
    return result


def resolve(text, projects, explicit=None):
    if explicit is not None:
        return [explicit] if explicit in projects else []
    text = normalize(text)
    matches = []
    for key, fields in projects.items():
        names = [key, *fields['aliases'].split('|')]
        # AWO is the command prefix, so it must not also select the AWO repo.
        names = [normalize(n) for n in names if normalize(n) not in ('', 'awo')]
        if any(re.search(r'(?<!\w)' + re.escape(n) + r'(?![a-zA-Z0-9_])', text)
               for n in names):
            matches.append(key)
    return matches


def in_progress(path):
    folder = Path(git(path, 'rev-parse', '--absolute-git-dir'))
    return any((folder / name).exists() for name in
               ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge',
                'rebase-apply', 'BISECT_LOG'))


def identity(path):
    folder = Path(git(path, 'rev-parse', '--absolute-git-dir'))
    stat = folder.stat()
    return [str(folder), stat.st_dev, stat.st_ino, (Path(path) / '.git').stat().st_mtime_ns]


def inspect(project):
    path = str(Path(project['path']).expanduser().resolve())
    base = project['base_ref']
    git(path, 'rev-parse', '--verify', base + '^{commit}')
    rows = records(path)
    for row in rows:
        wt = row['worktree']
        row['status'] = git(wt, 'status', '--porcelain=v1', '--untracked-files=all')
        row['changed_files'] = [n for n in git(wt, 'diff', '--no-ext-diff',
                                              '--no-textconv', '--name-only', '-z', base).split('\0') if n]
        row['in_progress'] = in_progress(wt)
    common = Path(git(path, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = Path(path) / common
    return path, rows, common.resolve() / 'awo' / 'tasks.json'


def load_tasks(file):
    tasks = json.loads(file.read_text()) if file.exists() else []
    if not isinstance(tasks, list) or any(not isinstance(t, dict) or
            not all(k in t for k in ('goal', 'path', 'branch', 'identity')) for t in tasks):
        raise RuntimeError('invalid task metadata; inspect before starting')
    for task in tasks:
        if not isinstance(task.get('goal'), str) or not task['goal'].strip():
            raise RuntimeError('invalid task goal')
        if task.get('schema_version', 1) != 1:
            raise RuntimeError('unsupported task schema')
        task.setdefault('id', 'legacy-' + hashlib.sha256(json.dumps(
            [task['goal'], task['path'], task['identity']], sort_keys=True).encode()).hexdigest()[:24])
        if not isinstance(task['id'], str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', task['id']):
            raise RuntimeError('invalid task ID')
        if task.get('path') is not None and (not isinstance(task['path'], str) or not Path(task['path']).is_absolute()):
            raise RuntimeError('invalid task path')
        if task.get('path') is None:
            if task['branch'] is not None or task['identity'] is not None:
                raise RuntimeError('unbound task has invalid identity')
        elif not isinstance(task['branch'], str) or not isinstance(task['identity'], list):
            raise RuntimeError('invalid task identity')
        if task.get('state', '확인필요') not in ('할일', '진행', '확인필요', '보관', '완료'):
            raise RuntimeError('invalid task state')
        if not isinstance(task.get('events', []), list) or any(not isinstance(e, dict) for e in task.get('events', [])):
            raise RuntimeError('invalid task history')
    if len({t['id'] for t in tasks}) != len(tasks):
        raise RuntimeError('duplicate task ID')
    return tasks


def active_tasks(tasks, rows):
    by_path = {r['worktree']: r for r in rows[1:]}
    active = []
    for task in tasks:
        try:
            if task['path'] in by_path and task['branch'] == by_path[task['path']].get('branch') and task['identity'] == identity(task['path']):
                active.append(task)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            continue
    return active


def decide(args, project, rows, tasks):
    if not args.goal or not args.goal.strip():
        return {'action': 'needs_goal', 'question': '어떤 기능이나 문제를 작업할까요?'}
    if any(row['in_progress'] for row in rows):
        return {'action': 'blocked', 'reason': 'Git operation in progress'}
    active = active_tasks(tasks, rows)
    matches = [t for t in active if normalize(t['goal']) == normalize(args.goal)]
    if args.worktree:
        path = str(Path(args.worktree).expanduser().resolve())
        selected = [r for r in rows[1:] if r['worktree'] == path]
        if not selected or any(k in selected[0] for k in ('locked', 'prunable', 'detached')):
            return {'action': 'blocked', 'reason': 'select an available non-primary branch worktree'}
        if matches and any(t['path'] != path for t in matches):
            return {'action': 'blocked', 'reason': 'goal is already associated with another worktree'}
        if any(t['path'] == path and normalize(t['goal']) != normalize(args.goal) for t in active):
            return {'action': 'blocked', 'reason': 'worktree belongs to a different goal'}
        return {'action': 'reuse', 'path': path}
    if len(matches) > 1:
        return {'action': 'needs_worktree', 'reason': 'multiple worktrees for this goal'}
    if matches:
        row = next(r for r in rows if r['worktree'] == matches[0]['path'])
        if any(k in row for k in ('locked', 'prunable', 'detached')):
            return {'action': 'blocked', 'reason': 'goal worktree is unavailable'}
        return {'action': 'reuse', 'path': matches[0]['path']}
    known = {t['path'] for t in active}
    if not args.new_goal and any(r['worktree'] not in known for r in rows[1:]):
        return {'action': 'needs_worktree', 'reason': 'inspect existing goals; use --worktree PATH or --new-goal'}
    limit = int(project['max_worktrees'])
    if len(rows) >= limit:
        return {'action': 'blocked', 'reason': f'worktree limit reached ({len(rows)}/{limit})'}
    task = args.task or 'task-' + hashlib.sha256(normalize(args.goal).encode()).hexdigest()[:12]
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', task):
        raise RuntimeError('task must be a lowercase ASCII slug')
    if any(r.get('branch', '').split('/')[-1] == task for r in rows):
        return {'action': 'blocked', 'reason': 'task name already in use; inspect existing worktree'}
    return {'action': 'create', 'task': task}


@contextmanager
def task_lock(file):
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('another AWO request is running for this repository') from exc
        yield


def execute(args, key, project, path, rows, file):
    from awo_state import project_lock, pending, event, acknowledge
    from awo_start import dispatch
    with project_lock(path), task_lock(file):
        if pending(path):
            raise RuntimeError("이전 실행 결과 미확인: task reconcile 필요")
        prepared = subprocess.run([str(ROOT / 'scripts/prepare-base.sh'), path, project['base_ref']],
                                  capture_output=True, text=True)
        if prepared.returncode:
            raise RuntimeError('base preparation failed: ' + prepared.stderr.strip())
        path, rows, file = inspect(project)
        tasks = load_tasks(file)
        decision = decide(args, project, rows, tasks)
        if decision['action'] == 'create':
            before = {r['worktree'] for r in rows}
            launch_args = argparse.Namespace(project=key, task=decision['task'], agent=args.agent,
                goal=args.goal, worktree=None, new_session=False)
            response, code = dispatch(launch_args, locked=True)
            receipt = response.get('awo_dispatch', {})
            if code:
                raise RuntimeError('Orca refused creation: ' + receipt.get('reason', '실행 미확인'))
            decision['dispatch'] = receipt
            new = [r for r in records(path) if r['worktree'] not in before]
            if len(new) != 1:
                raise RuntimeError('cannot confirm created path; inspect worktrees before retry')
            wt = new[0]['worktree']
            if subprocess.run(['git', '-C', wt, 'merge-base', '--is-ancestor',
                               project['base_ref'], 'HEAD'], capture_output=True).returncode:
                raise RuntimeError('created worktree does not contain configured base')
            decision.update(path=wt)
        if decision['action'] in ('create', 'reuse'):
            wt = decision['path']
            row = next(r for r in records(path) if r['worktree'] == wt)
            task = next((t for t in tasks if t['path'] == wt), None)
            if task is None:
                task = next((t for t in tasks if t['path'] is None and normalize(t['goal']) == normalize(args.goal)), None)
            if task is None:
                task = {}
                tasks.append(task)
            task.update(goal=args.goal.strip(), path=wt, branch=row['branch'], identity=identity(wt), project=key)
            if decision['action'] == 'reuse' and args.agent != 'none':
                launch_args = argparse.Namespace(project=key, task='resume', agent=args.agent,
                    goal=args.goal, worktree=wt, new_session=False)
                response, code = dispatch(launch_args, locked=True)
                decision['dispatch'] = response['awo_dispatch']
            task['state'] = '진행' if decision.get('dispatch', {}).get('state') == 'session_confirmed' else '확인필요'
            event(task, 'request', action_result=decision['action'])
            save(file, tasks)
            acknowledge(path)
        return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('text')
    parser.add_argument('--project')
    parser.add_argument('--goal', help='concrete goal extracted by supervising agent')
    parser.add_argument('--task')
    parser.add_argument('--worktree', help='existing same-goal path, confirmed by supervisor')
    parser.add_argument('--new-goal', action='store_true', help='existing unregistered worktrees were checked')
    parser.add_argument('--agent', default='none', choices=['none', 'codex', 'claude'])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--advise', choices=['none', 'jev'], default='none',
                        help='opt in to external candidate advice in preview only')
    parser.add_argument('--advice-cohort', choices=['production', 'smoke'], default='production',
                        help='separate synthetic/smoke observations from real work')
    args = parser.parse_args()
    projects = registry()
    matches = resolve(args.text, projects, args.project)
    if len(matches) != 1:
        report = {'action': 'needs_project', 'candidates': matches,
                  'registered_projects': list(projects)}
        from awo_advice import advise
        report['advisory'] = advise(args, projects, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    key = matches[0]
    project = projects[key]
    path, rows, file = inspect(project)
    tasks = load_tasks(file)
    decision = decide(args, project, rows, tasks)
    if args.apply and decision['action'] in ('create', 'reuse'):
        decision = execute(args, key, project, path, rows, file)
        path, rows, file = inspect(project)
        tasks = load_tasks(file)
    report = {'project': key, 'repo_path': path, 'base_ref': project['base_ref'],
              'mode': 'APPLY' if args.apply else 'PREVIEW', 'worktrees': rows,
              'known_goals': active_tasks(tasks, rows), **decision}
    from awo_advice import advise
    report['advisory'] = advise(args, projects, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if decision['action'] == 'blocked' else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
