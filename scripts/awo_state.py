"""Shared, durable local ownership. Reads never create metadata."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import uuid

from awo_audit import git, save


def now():
    return datetime.now(timezone.utc).isoformat()


def folder(repo):
    common = Path(git(repo, 'rev-parse', '--git-common-dir'))
    return (common if common.is_absolute() else Path(repo) / common).resolve() / 'awo'


@contextmanager
def project_lock(repo):
    file = folder(repo).parent / 'awo-dispatch.lock'
    with file.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('다른 AWO 작업이 실행 중입니다. 기존 작업을 확인하세요.') from exc
        yield


def event(task, action, **details):
    task.setdefault('id', 'task-' + uuid.uuid4().hex)
    task['schema_version'] = 1
    task.setdefault('created_at', now())
    task['updated_at'] = now()
    task.setdefault('events', []).append({'at': task['updated_at'], 'action': action, **details})
    return task


def pending(repo):
    file = folder(repo) / 'dispatch.json'
    if not file.exists():
        return None
    value = json.loads(file.read_text())
    if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('state') not in (
            'pending', 'unverified', 'worktree_only', 'session_confirmed', 'idle', 'existing_terminal', 'reconciled'):
        raise RuntimeError('실행 소유 기록이 손상됐습니다. 수동 확인이 필요합니다.')
    return value if value.get('state') in ('pending', 'unverified') or value.get('registration_pending') else None


def acknowledge(repo):
    file = folder(repo) / 'dispatch.json'
    if not file.exists():
        return
    value = json.loads(file.read_text())
    if value.get('state') not in ('pending', 'unverified'):
        value['registration_pending'] = False
        save(file, value)


def dispatch_locked(args, primary, base, agent, task, launch):
    if pending(primary):
        raise RuntimeError('이전 실행 결과가 미확인입니다. task reconcile로 확인하기 전 재실행하지 않습니다.')
    file = folder(primary) / 'dispatch.json'
    intent = dict(schema_version=1, state='pending', at=now(), task=task,
                  goal=args.goal, path=args.worktree, agent=agent)
    attempted = False

    def before_create():
        nonlocal attempted
        save(file, intent)  # durable immediately before the first external creation
        attempted = True

    result, code = launch(args, primary, base, agent, task, before_create=before_create)
    if attempted:
        receipt = result.get('awo_dispatch', {})
        intent.update(state=receipt.get('state', 'unverified'), receipt=receipt, updated_at=now(), registration_pending=True)
        save(file, intent)
    return result, code
