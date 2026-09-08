#!/usr/bin/env python3
"""Dispatch work to an independent Orca terminal, never the caller's session."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from awo_audit import config, git, records


def orca(*args):
    p = subprocess.run(['orca', *args, '--json'], capture_output=True, text=True, timeout=5 if args[:2] == ('terminal', 'show') else 40)
    if p.returncode:
        raise RuntimeError('Orca command failed: ' + ' '.join(args[:2]))
    try:
        value = json.loads(p.stdout)
    except ValueError:
        raise RuntimeError('Orca did not return JSON')
    if not isinstance(value, dict) or value.get('ok') is False:
        raise RuntimeError('Unexpected Orca response')
    return value


def payload(value):
    result = value.get('result', value)
    if not isinstance(result, dict):
        raise RuntimeError('Invalid Orca result metadata')
    return result


def terminal(value):
    return payload(value).get('terminal', {})


def validate_worktree(primary, target):
    primary = Path(records(primary)[0]['worktree'])
    found = next((r for r in records(primary) if Path(r['worktree']) == target), None)
    if not found or target == primary or 'locked' in found or 'prunable' in found:
        raise RuntimeError('Target must be an existing, unlocked non-primary worktree of this project')
    if Path(git(target, 'rev-parse', '--show-toplevel')).resolve() != target:
        raise RuntimeError('Worktree path does not match Git identity')
    branch = git(target, 'symbolic-ref', '--short', 'HEAD')
    if found.get('branch') != 'refs/heads/' + branch:
        raise RuntimeError('Worktree branch identity mismatch')
    gd = Path(git(target, 'rev-parse', '--absolute-git-dir'))
    if any((gd / n).exists() for n in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')):
        raise RuntimeError('Git operation in progress in target worktree')
    return branch


def dispatch(args):
    if args.new_session and not args.worktree:
        raise RuntimeError('--new-session requires --worktree')
    primary = Path(config(args.project, 'path')).expanduser().resolve()
    if Path(git(primary, 'rev-parse', '--show-toplevel')).resolve() != primary:
        raise RuntimeError('Configured project must be a Git checkout root')
    primary = Path(records(primary)[0]['worktree'])
    base = config(args.project, 'base_ref', 'origin/main')
    agent = args.agent or config(args.project, 'default_agent', 'codex')
    task = re.sub('-+', '-', re.sub('[^a-z0-9._-]+', '-', args.task.lower())).strip('-')
    if not task or task.startswith('.'):
        raise RuntimeError('Task name must contain a valid non-hidden name')
    git(primary, 'check-ref-format', '--branch', task)
    # Serialize AWO launches across all worktrees of the project.
    common = Path(git(primary, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = primary / common
    with open(common / 'awo-dispatch.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return launch(args, primary, base, agent, task)


def launch(args, primary, base, agent, task):
    receipt = {'coordinator_instruction': 'Do not implement in the coordinator session; continue only in the independent worker.', 'state': 'unverified', 'agent': agent, 'reason': '', 'terminal_id': None}
    raw = {}
    if args.worktree:
        target = Path(args.worktree).expanduser().resolve()
        branch = validate_worktree(primary, target)
        listing = payload(orca('terminal', 'list', '--worktree', 'path:' + str(target)))
        items = listing.get('terminals')
        if not isinstance(items, list) or listing.get('truncated'):
            raise RuntimeError('Cannot inspect existing terminals; refusing duplicate worker')
        known_agent = any(not isinstance(item, dict) or item.get('agentIdentity') for item in items)
        if items and (known_agent or not args.new_session):
            receipt.update(state='existing_terminal', path=str(target), branch=branch,
                           reason='Existing terminal(s) found; no worker created and no prompt sent')
            return {'awo_dispatch': receipt}, 3
        if items:
            receipt['warning'] = 'Existing terminals preserved; user explicitly authorized a separate session despite unknown agent identities'
        if agent not in ('codex', 'claude'):
            raise RuntimeError('Existing-worktree dispatch supports codex or claude only')
        command = shlex.join([agent] + (['--', args.goal] if args.goal else []))
        try:
            raw = orca('terminal', 'create', '--worktree', 'path:' + str(target), '--command', command)
        except (RuntimeError, subprocess.SubprocessError, OSError):
            receipt.update(path=str(target), branch=branch, reason='Terminal creation outcome unknown; inspect Orca before retrying')
            return {'awo_dispatch': receipt}, 3
        try:
            created_terminal = terminal(raw)
            handle = created_terminal.get('handle') if isinstance(created_terminal, dict) else None
        except RuntimeError:
            handle = None
    else:
        gd = Path(git(primary, 'rev-parse', '--absolute-git-dir'))
        if any((gd / n).exists() for n in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')):
            raise RuntimeError('Git operation in progress in primary checkout')
        rows = records(primary)
        if any(r.get('branch') == 'refs/heads/' + task for r in rows):
            raise RuntimeError('Task worktree already exists; use --worktree PATH')
        if len(rows) >= int(config(args.project, 'max_worktrees', '3')):
            raise RuntimeError('Worktree limit reached')
        subprocess.run(['git', '-C', str(primary), 'fetch', '--prune', 'origin'],
                       check=True, capture_output=True, timeout=40)
        git(primary, 'rev-parse', '--verify', base + '^{commit}')
        rid = subprocess.run([str(Path(__file__).parent / 'orca-repo-id.sh'), str(primary)],
                             capture_output=True, text=True, check=True, timeout=40).stdout.strip()
        argv = ['worktree', 'create', '--repo', 'id:' + rid, '--name', task,
                '--setup', 'run', '--base-branch', base, '--no-parent', '--agent', agent]
        if args.goal:
            argv += ['--prompt', args.goal]
        try:
            raw = orca(*argv)
        except (RuntimeError, subprocess.SubprocessError, OSError):
            receipt.update(reason='Worktree creation outcome unknown; inspect Orca before retrying')
            return {'awo_dispatch': receipt}, 3
        try:
            result = payload(raw)
        except RuntimeError:
            receipt['reason'] = 'Creation response could not be verified; inspect Orca before retrying'
            raw['awo_dispatch'] = receipt
            return raw, 3
        wt = result.get('worktree') or {}
        path = (wt.get('path') or wt.get('worktreePath')) if isinstance(wt, dict) else None
        if not isinstance(path, str) or not Path(path).is_absolute():
            receipt['reason'] = 'Worktree response has no verifiable path; inspect Orca before retrying'
            raw['awo_dispatch'] = receipt
            return raw, 3
        target = Path(path).resolve()
        if any(Path(row['worktree']) == target for row in rows):
            receipt.update(path=str(target), reason='Creation returned a preexisting worktree; worker ownership is unverified')
            raw['awo_dispatch'] = receipt
            return raw, 3
        try:
            branch = validate_worktree(primary, target)
        except (RuntimeError, OSError):
            receipt.update(path=str(target), reason='Created path could not be verified; inspect Orca before retrying')
            raw['awo_dispatch'] = receipt
            return raw, 3
        startup = result.get('startupTerminal') or {}
        handle = (startup.get('handle') if isinstance(startup, dict) else None) or result.get('agentTerminalHandle')
        if result.get('agentTerminalHandle') and result.get('agentTerminalHandle') != handle:
            handle = None
    receipt.update(path=str(target), branch=branch, terminal_id=handle)
    if not isinstance(handle, str) or not handle.strip():
        receipt['reason'] = 'No exact terminal handle returned; inspect Orca before retrying'
    else:
        try:
            observed = {}
            for attempt in range(6):
                observed = terminal(orca('terminal', 'show', '--terminal', handle))
                if not isinstance(observed, dict):
                    raise RuntimeError('Invalid terminal metadata')
                if observed.get('connected') and observed.get('agentIdentity') == agent:
                    break
                if attempt < 5:
                    time.sleep(1)
            if (observed.get('worktreePath') != str(target) or observed.get('branch') != branch
                    or observed.get('handle') != handle):
                raise RuntimeError('Terminal worktree identity mismatch')
            if not observed.get('connected') or observed.get('agentIdentity') != agent:
                receipt['reason'] = 'Terminal exists but connected agent identity is not confirmed'
            else:
                receipt['state'] = 'session_confirmed' if args.goal else 'idle'
                receipt['reason'] = ('Independent agent confirmed; prompt supplied at creation; task progress not verified'
                                     if args.goal else 'Independent agent confirmed; no task goal supplied')
        except (RuntimeError, subprocess.TimeoutExpired):
            receipt['reason'] = 'Terminal verification unavailable; inspect Orca before retrying'
    raw['awo_dispatch'] = receipt
    return raw, 3 if receipt['state'] == 'unverified' else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('task')
    parser.add_argument('agent', nargs='?')
    parser.add_argument('goal', nargs='?', default='')
    parser.add_argument('--worktree', help='Reuse an existing non-primary worktree without duplication')
    parser.add_argument('--new-session', action='store_true', help='With --worktree, authorize a new agent alongside terminals of unknown identity; known agents still block')
    args = parser.parse_args()
    try:
        output, code = dispatch(args)
        print(json.dumps(output, ensure_ascii=False))
        return code
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else 'Dispatch failed; inspect Orca before retrying; no coordinator fallback was run'
        print('ERROR: ' + message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
