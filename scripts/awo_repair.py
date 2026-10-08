"""Explicit, snapshot-bound repair of device-only binding drift."""
import copy
import hashlib
import json
from pathlib import Path

from awo_audit import git, records, save
from awo_request import identity
from awo_start import validate_worktree
from awo_state import event, folder


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def diagnose(repo, task):
    stored = {k: copy.deepcopy(task.get(k)) for k in ('id', 'path', 'branch', 'identity')}
    out = {'stored': stored, 'current': None, 'repairable': False, 'reason': '확인필요: device 이외 변경은 자동 복구하지 않습니다.'}
    try:
        path = task['path']
        if not path or str(Path(path).resolve()) != path:
            raise RuntimeError('기록 경로 불일치')
        branch = 'refs/heads/' + validate_worktree(Path(repo), Path(path))
        common = str(folder(repo).parent)
        if str(folder(path).parent) != common:
            raise RuntimeError('Git common-dir 불일치')
        registration = next(r for r in records(repo) if r['worktree'] == path)
        current = {'id': task['id'], 'path': path, 'branch': branch, 'identity': identity(path)}
        out.update(current=current, evidence={'common_dir': common, 'registration': registration,
                   'head': git(path, 'rev-parse', 'HEAD')})
        old, new = stored['identity'], current['identity']
        if stored == current:
            out.update(reason='verified', verified=True)
        elif (isinstance(old, list) and len(old) == len(new) == 4
              and stored['branch'] == branch and old[1] != new[1]
              and all(old[i] == new[i] for i in (0, 2, 3))):
            out.update(repairable=True, reason='device만 변경: preview snapshot을 확인한 뒤 repair --apply --snapshot TOKEN')
    except (RuntimeError, OSError, ValueError, KeyError, StopIteration) as exc:
        out['reason'] = str(exc)
    out['snapshot'] = digest(out)
    return out


def repair(args, repo, file, tasks, task):
    report = diagnose(repo, task)
    report['mode'] = 'APPLY' if args.apply else 'PREVIEW'
    if not args.apply:
        return report
    if not args.snapshot or args.snapshot != report['snapshot']:
        raise RuntimeError('진단 snapshot이 없거나 변경되었습니다. task diagnose 후 다시 확인하세요.')
    if not report['repairable']:
        raise RuntimeError(report['reason'])
    fresh = diagnose(repo, task)
    if fresh['snapshot'] != report['snapshot']:
        raise RuntimeError('복구 직전 snapshot 변경: 적용하지 않습니다.')
    task['identity'] = fresh['current']['identity']
    event(task, 'identity-repair', previous=fresh['stored'], current=fresh['current'],
          evidence=fresh['evidence'], snapshot=fresh['snapshot'])
    save(file, tasks)
    return dict(report, repaired=True, task_id=task['id'])
