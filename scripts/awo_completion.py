"""Explicit, durable finish orchestration. No merge or push operations."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

import awo_audit as audit
from awo_repair import digest
from awo_state import event, now, pending

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    return audit.git(path, *args)


def snapshot(path, preservation=False):
    """Content evidence for tracked/nonignored files, independent of build-cache mtimes."""
    names = set()
    for flags in (('--cached',), ('--others', '--exclude-standard')):
        names.update(n for n in git(path, 'ls-files', '-z', *flags).split('\0') if n)
    files = {}
    for name in sorted(names):
        file = Path(path) / name
        try:
            info = file.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            content = os.readlink(file).encode()
        elif stat.S_ISREG(info.st_mode):
            h = hashlib.sha256()
            with file.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            content = h.digest()
        else:
            raise RuntimeError('디렉터리/submodule/특수 파일은 수동 검증이 필요합니다: ' + name)
        files[name] = [stat.S_IMODE(info.st_mode), hashlib.sha256(content).hexdigest()]
    from awo_request import identity
    result = {'head': git(path, 'rev-parse', 'HEAD'), 'identity': identity(path),
              'branch': git(path, 'symbolic-ref', 'HEAD'), 'files': digest(files),
              'index': digest(git(path, 'ls-files', '--stage', '-z')),
              'flags': digest([f for f in git(path, 'ls-files', '-v', '-z').split('\0') if f and (f[0].islower() or f[0] == 'S')]),
              'status': git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=all')}
    if preservation:
        ignored = {}
        for name in git(path, 'ls-files', '--others', '--ignored', '--exclude-standard', '-z').split('\0'):
            if name:
                st = (Path(path) / name).lstat()
                ignored[name] = [st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
        result['ignored_inventory'] = digest(ignored)
    return result


def validation_current(task, current):
    evidence = task.get('finish', {}).get('validation', {})
    return evidence.get('state') == 'passed' and evidence.get('snapshot') == current


def removed_confirmed(repo, task):
    return (task.get('finish', {}).get('cleanup', {}).get('state') == 'removed'
            and not Path(task['path']).exists()
            and all(r['worktree'] != task['path'] for r in audit.records(repo)))


def finish_preview(args, repo, task, sessions=None, cleanup_rows=None):
    from awo_lifecycle import verify, projects, cleanup_preview, session_snapshot, sessions_at
    report = {'mode': 'PREVIEW', 'task_id': task['id'], 'path': task.get('path'),
              'result': copy.deepcopy(task.get('finish', {}).get('result', {'state': 'pending'})),
              'validation': {'state': 'required', 'source': 'executed evidence required'},
              'commit': copy.deepcopy(task.get('finish', {}).get('commit', {'state': 'not_requested'})),
              'integration': {'state': 'unknown'}, 'session': {'state': 'unknown'},
              'cleanup': {'state': 'pending'}, 'remaining': [],
              'user_validation': copy.deepcopy(task.get('finish', {}).get('user_validation')),
              'requested': {k: getattr(args, k, None) for k in ('validate', 'file', 'message', 'close', 'cleanup')}}
    if task.get('path') and removed_confirmed(repo, task):
        report.update(cleanup=copy.deepcopy(task['finish']['cleanup']),
                      validation=copy.deepcopy(task['finish'].get('validation', {})),
                      integration=copy.deepcopy(task['finish'].get('integration', {})))
        report['session'] = sessions_at(sessions if sessions is not None else session_snapshot(), task['path'])
        report['label'] = '완료·정리됨'
        return report
    try:
        verify(repo, task)
        current = snapshot(task['path'])
        report['snapshot'] = current
        report['validation'] = copy.deepcopy(task.get('finish', {}).get('validation', report['validation']))
        if not validation_current(task, current):
            report['validation']['state'] = 'required'
            report['remaining'].append('검증 필요: --apply --validate COMMAND (사용자 제공 결과는 실행 증거가 아님)')
            report['result']['state'] = 'pending'
        base = projects()[args.project][1]
        base_head = git(repo, 'rev-parse', '--verify', base + '^{commit}')
        proc = subprocess.run(['git', '-C', task['path'], 'merge-base', '--is-ancestor', current['head'], base_head], capture_output=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError('통합 상태 조회 실패')
        report['integration'] = {'state': 'contained' if proc.returncode == 0 else 'merge_pending',
                                 'base_ref': base, 'base_head': base_head, 'head': current['head'],
                                 'source': 'local refs; read-only; no fetch/merge/push'}
        if proc.returncode:
            report['remaining'].append('완료 후 병합대기: configured base의 수동 통합/검토 필요')
        if current['status']:
            report['remaining'].append('미커밋 변경 보존: 명시 파일 커밋 또는 수동 보관 확인 필요')
        report['session'] = sessions_at(sessions if sessions is not None else session_snapshot(), task['path'])
        report['session']['finish_action'] = copy.deepcopy(task.get('finish', {}).get('session', {}))
        if report['session']['state'] != 'absent':
            report['remaining'].append('세션 종료 대기: --close --next TEXT --processes-checked 및 idle/draft/identity 검사 필요')
        # The board supplies its one optional project-wide inspection. An empty
        # mapping preserves the default board's no-detailed-cleanup contract.
        rows = cleanup_rows if cleanup_rows is not None else cleanup_preview(args.project, repo, base, audit.records(repo))
        row = rows.get(task['path'])
        if row is None:
            row = {'classification': 'UNKNOWN', 'reasons': ['미검사: board --cleanup 또는 task finish로 정리 조건을 확인하세요.']}
        reasons = row['reasons'] or [{
            'ACTIVE': '최근 생성/활동 24h 보호: 폴더 정리대기',
            'ACTIVE_IDLE': '최근 생성/활동 72h 보호: 폴더 정리대기',
            'SAFE_CLEANUP': '정리 후보: --apply --cleanup --processes-checked에서 재검사',
        }.get(row['classification'], row['classification'])]
        report['cleanup'] = {'state': 'pending', 'inspection': row, 'reasons': reasons,
                             'command': ['awo', 'cleanup', args.project, '--worktree', task['path'], '--apply', '--json']}
        report['remaining'].append('폴더 정리 대기: ' + '; '.join(reasons))
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        report['remaining'].append(str(exc))
        report['result']['state'] = 'pending'
    report['label'] = ('완료·병합대기' if report['result'].get('state') == 'complete'
                       and report['integration']['state'] == 'merge_pending' else
                       '완료·정리대기' if report['result'].get('state') == 'complete' else '마무리 대기')
    return report


def selected_files(args, path, task):
    """Ledger is corroboration, never authorization or a proof of exclusive ownership."""
    if not args.message or not args.ownership_checked:
        raise RuntimeError('커밋은 --message, --ownership-checked가 필요합니다.')
    chosen = sorted(set(args.file))
    if len(chosen) != len(args.file):
        raise RuntimeError('중복 파일 선택')
    for name in chosen:
        p = Path(name)
        if (not name or p.is_absolute() or '..' in p.parts or str(p) != name or name == '.'
                or '.git' in p.parts or (Path(path) / name).is_dir()
                or (Path(path) / name).is_symlink()
                or not (Path(path) / name).resolve().is_relative_to(Path(path))):
            raise RuntimeError('개별 상대 파일만 선택하세요 (폴더/pathspec/symlink 불가): ' + name)
    flags = git(path, 'ls-files', '-v', '-z').split('\0')
    if any(f and (f[0].islower() or f[0] == 'S') for f in flags):
        raise RuntimeError('숨긴 index flags: 커밋 차단')
    changed = set(n for n in git(path, 'diff', 'HEAD', '--name-only', '-z', '--no-renames').split('\0') if n)
    changed.update(n for n in git(path, 'ls-files', '--others', '--exclude-standard', '-z').split('\0') if n)
    if changed != set(chosen):
        raise RuntimeError('선택 밖 변경 또는 변경 없는 파일: 기존 파일을 보존하고 커밋을 거부합니다.')
    staged = git(path, 'diff', '--cached', '--name-only', '-z')
    receipt = task.get('finish', {}).get('commit', {})
    if staged and not (receipt.get('state') == 'staged' and receipt.get('files') == chosen
                       and receipt.get('owner_session') == args.owner_session
                       and receipt.get('message') == args.message
                       and receipt.get('snapshot') == snapshot(path)):
        raise RuntimeError('기존 staged 변경 보존: 자동 커밋하지 않습니다.')
    return chosen


def finish(args, repo, file, tasks, task):
    from awo_lifecycle import verify, handoff, park_close, session_snapshot, sessions_at
    if args.timeout <= 0:
        raise RuntimeError('--timeout은 양수여야 합니다.')
    if removed_confirmed(repo, task):
        return dict(finish_preview(args, repo, task), mode='APPLY')
    verify(repo, task)
    if pending(repo):
        raise RuntimeError('미확인 실행 기록: task reconcile 필요')
    state = task.setdefault('finish', {})
    def record(stage, value):
        state[stage] = value
        event(task, 'finish-' + stage, evidence=copy.deepcopy(value))
        audit.save(file, tasks)
    def blocked(reason):
        record('result', {'state': 'pending', 'reason': reason, 'at': now()})
        report = finish_preview(args, repo, task)
        report.update(mode='APPLY', blocked=reason)
        return report
    if args.validation:
        record('user_validation', {'source': '사용자 제공', 'result': args.validation, 'at': now()})
    path = task['path']
    current = snapshot(path)
    # A possibly successful commit interrupted before receipt persistence needs review.
    if state.get('commit', {}).get('state') == 'attempting':
        receipt = state['commit']
        if not args.reconcile_commit:
            return blocked('이전 커밋 결과 미확인: HEAD/index 검토 후 --reconcile-commit. 자동 재커밋하지 않습니다.')
        staged = receipt.get('snapshot', {})
        parents = git(path, 'rev-list', '--parents', '-n', '1', 'HEAD').split()
        if (parents[1:] == [receipt.get('before_head')]
                and git(path, 'rev-parse', 'HEAD^{tree}') == receipt.get('expected_tree')
                and all(current.get(k) == staged.get(k) for k in ('identity', 'branch', 'files', 'flags'))
                and not current['status']):
            record('commit', dict(receipt, state='committed', head=current['head'], snapshot=current, reconciled_at=now()))
        elif current == staged:
            record('commit', dict(receipt, state='staged', reconciled_at=now()))
        else:
            return blocked('커밋 결과가 보존된 HEAD/tree/파일과 다릅니다. 수동 검토 필요')
        # Reconciliation never commits or closes in this invocation.
        return blocked('커밋 결과 대조 완료. 다음 호출에서 --validate로 현재 HEAD를 검증하세요.')
    if (state.get('validation', {}).get('state') == 'failed'
            and any(r.get('error', '').startswith('timeout') for r in state['validation'].get('runs', []))
            and not args.processes_checked):
        return blocked('이전 검증 timeout: 남은 프로세스 확인 후 --processes-checked 필요')
    if args.validate and not (validation_current(task, current)
                              and state['validation'].get('commands') == args.validate):
        evidence = {'state': 'running', 'source': 'executed', 'commands': args.validate,
                    'runs': [], 'snapshot': current, 'at': now()}
        record('validation', evidence)
        for command in args.validate:
            before = snapshot(path)
            if before != current:
                evidence['state'] = 'stale'
                record('validation', evidence)
                return blocked('검증 시작 전 작업폴더 변경: 새 검증 필요')
            run = {'command': command, 'cwd': path, 'head': current['head'], 'started_at': now()}
            evidence['runs'].append(run)
            record('validation', evidence)  # persist attempted command before execution
            started = time.monotonic()
            try:
                # Commands are explicitly supplied by the caller. Never persist output/secrets.
                proc = subprocess.run(command, shell=True, cwd=path, timeout=args.timeout,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                run['exit_code'] = proc.returncode
            except subprocess.TimeoutExpired:
                run.update(exit_code=None, error='timeout; check child processes before retry')
            except OSError:
                run.update(exit_code=None, error='execution failed')
            run.update(finished_at=now(), duration_seconds=round(time.monotonic() - started, 3))
            verify(repo, task)
            after = snapshot(path)
            evidence['state'] = 'failed' if run['exit_code'] != 0 else 'stale' if after != before else 'running'
            record('validation', evidence)
            if evidence['state'] != 'running':
                return blocked('검증 실패 또는 검증 중 파일 변경: commit/close/cleanup 차단')
        evidence.update(state='passed', snapshot=snapshot(path))
        record('validation', evidence)
    current = snapshot(path)
    if not validation_current(task, current):
        return blocked('현재 HEAD/파일의 실행 검증 필요: --validate COMMAND')
    if args.file:
        prior = state.get('commit', {})
        if not (prior.get('state') == 'committed' and prior.get('head') == current['head']
                and not current['status'] and prior.get('files') == sorted(set(args.file))
                and prior.get('message') == args.message and prior.get('owner_session') == args.owner_session):
            try:
                chosen = selected_files(args, path, task)
                verify(repo, task)
                if snapshot(path) != current:
                    raise RuntimeError('커밋 전 snapshot 변경')
                receipt = {'state': 'preparing', 'files': chosen, 'message': args.message,
                           'owner_session': args.owner_session, 'ownership_checked': True,
                           'ledger_notice': 'historical observation is not ownership proof; caller confirmed current selected changes',
                           'before_head': current['head'], 'at': now()}
                record('commit', receipt)
                specs = [':(literal)' + n for n in chosen]
                git(path, 'add', '--', *specs)
                staged = snapshot(path)
                receipt.update(state='staged', snapshot=staged)
                record('commit', receipt)
                # Staging is expected; all actual content, HEAD and binding must remain identical.
                if any(staged[k] != current[k] for k in ('head', 'identity', 'branch', 'files', 'flags')):
                    raise RuntimeError('staging 중 파일 변경: staged 보존, 새 검증 필요')
                expected_tree = git(path, 'write-tree')
                verify(repo, task)
                if snapshot(path) != staged:
                    raise RuntimeError('커밋 직전 snapshot 변경')
                receipt.update(state='attempting', expected_tree=expected_tree)
                record('commit', receipt)
                git(path, 'commit', '-m', args.message)
                after = snapshot(path)
                parents = git(path, 'rev-list', '--parents', '-n', '1', 'HEAD').split()
                if (parents[1:] != [current['head']] or git(path, 'rev-parse', 'HEAD^{tree}') != expected_tree
                        or any(after[k] != current[k] for k in ('identity', 'branch', 'files', 'flags'))):
                    raise RuntimeError('커밋 결과/후크 변경 확인 필요: 재검증 전 종료/정리 차단')
                receipt.update(state='committed', head=after['head'], snapshot=after)
                record('commit', receipt)
                # Evidence records the tested pre-commit HEAD and exact resulting commit tree.
                evidence = copy.deepcopy(state['validation'])
                evidence.update(snapshot=after, committed_head=after['head'], committed_tree=expected_tree)
                record('validation', evidence)
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                return blocked(str(exc))
    verify(repo, task)
    current = snapshot(path)
    if not validation_current(task, current):
        return blocked('마무리 직전 변경: 새 검증 필요')
    if current['status']:
        return blocked('미커밋 파일 보존: 커밋 또는 보관 처리 후 다시 finish 하세요.')
    record('result', {'state': 'complete', 'head': current['head'], 'at': now()})
    task['state'] = '완료'  # execution environment is recorded separately
    task['next'] = args.next or task.get('next') or '수동 통합 검토 후 정리 미리보기'
    task['validation'] = {'source': 'executed', 'result': 'passed', 'head': current['head'], 'at': now()}
    handoff(repo, task, 'finish')
    audit.save(file, tasks)
    if args.close:
        if sessions_at(session_snapshot(), path)['state'] == 'absent':
            record('session', {'state': 'absent', 'at': now()})
        else:
            try:
                close_args = copy.copy(args)
                close_args.validation = '실행 검증 통과: ' + current['head']
                park_close(close_args, repo, file, tasks, task, completed=True)
                record('session', copy.deepcopy(task['close']))
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                record('session', {'state': 'pending', 'reason': str(exc), 'at': now()})
    report = finish_preview(args, repo, task)
    record('integration', report['integration'])
    if args.cleanup:
        cleanup = report['cleanup']
        if (report['integration']['state'] != 'contained'
                or cleanup.get('inspection', {}).get('classification') != 'SAFE_CLEANUP'
                or sessions_at(session_snapshot(), path)['state'] != 'absent'
                or not args.processes_checked):
            cleanup['reason'] = '통합/기존 cleanup 보호/세션 부재/--processes-checked 모두 필요'
            record('cleanup', cleanup)
        else:
            verify(repo, task)
            if snapshot(path) != current:
                return blocked('정리 직전 파일 변경: 보존합니다.')
            handoff(repo, task, 'finish-cleanup')
            record('cleanup', dict(cleanup, state='attempting'))
            proc = subprocess.run([str(ROOT / 'bin/awo'), 'cleanup', args.project, '--worktree', path,
                                   '--apply', '--json'], capture_output=True, text=True)
            try:
                data = json.loads(proc.stdout)
                rows = data['worktrees']
                removed = proc.returncode == 0 and len(rows) == 1 and rows[0].get('path') == path and rows[0].get('removed') is True
            except (ValueError, KeyError, TypeError):
                removed = False
            record('cleanup', dict(cleanup, state='removed' if removed else 'pending',
                                   exit_code=proc.returncode, at=now(),
                                   reason='기존 cleanup CLI 결과 검증' if removed else 'cleanup 실패/보호 거부: 기존 CLI preview로 확인'))
    report = finish_preview(args, repo, task)
    report['mode'] = 'APPLY'
    return report
