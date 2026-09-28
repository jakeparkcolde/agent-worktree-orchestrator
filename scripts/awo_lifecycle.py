#!/usr/bin/env python3
"""작업판, 할일과 보관/재개. Git 파일과 프로세스는 변경하지 않습니다."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid

import awo_audit as audit
from awo_report import project_list, projects_file
from awo_request import identity, load_tasks, task_lock
from awo_start import validate_worktree, orca, payload, dispatch
from awo_state import folder, now, event, project_lock, pending, acknowledge

STATES = ('할일', '진행', '확인필요', '보관', '완료')


def projects():
    found = {key: (str(Path(path).expanduser().resolve()), base)
             for key, path, base in project_list()}
    # A malformed/missing path must remain visible instead of disappearing.
    for key in re.findall(r'^  ([A-Za-z0-9._-]+):\s*$', projects_file().read_text(), re.M):
        found.setdefault(key, (None, 'origin/main'))
    return found


def read_tasks(repo):
    return load_tasks(folder(repo) / 'tasks.json')


def session_snapshot():
    try:
        data = payload(orca('terminal', 'list'))
        rows = data.get('terminals')
        if not isinstance(rows, list) or data.get('truncated') or any(
                not isinstance(r, dict) or not r.get('worktreePath') or not r.get('handle') for r in rows):
            raise RuntimeError('불완전한 터미널 목록')
        return {'state': 'known', 'terminals': rows}
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return {'state': 'unknown', 'terminals': [], 'reason': '세션 조회 실패/불완전: 실행 여부를 확인하세요.'}


def sessions_at(snapshot, path):
    if snapshot['state'] != 'known':
        return {'state': 'unknown', 'terminals': []}
    rows = [r for r in snapshot['terminals'] if str(Path(r['worktreePath']).resolve()) == path]
    return {'state': 'present' if rows else 'absent',
            'terminals': [{k: r.get(k) for k in ('handle', 'agentIdentity', 'connected', 'branch')} for r in rows]}


def verify(repo, task):
    if not task.get('path'):
        raise RuntimeError('작업폴더가 없습니다. awo request --project KEY --goal 기록된목표 로 미리보기 후 --apply로 명시 시작하거나 task bind로 기존 폴더를 연결하세요.')
    branch = validate_worktree(Path(repo), Path(task['path']))
    if task['identity'] != identity(task['path']) or task['branch'] != 'refs/heads/' + branch:
        raise RuntimeError('작업폴더 경로/브랜치 identity가 바뀌었습니다. 자동 재연결하지 않습니다.')
    return branch


def cleanup_preview(key, repo, base, rows):
    file = folder(repo) / 'worktrees.json'
    state = json.loads(file.read_text()) if file.exists() else {}
    current = time.time()
    if not isinstance(state, dict) or any(not isinstance(v, dict) or any(
            not isinstance(v.get(k), (float, int)) or not math.isfinite(v[k]) or not 0 <= v[k] <= current
            for k in ('first_seen_at', 'last_activity_at')) for v in state.values()):
        raise RuntimeError('정리 메타데이터 손상: 정리 불가')
    thresholds = tuple(float(audit.config(key, k, str(v))) for k, v in
                       [('active_hours', 24), ('recent_hours', 72), ('stale_hours', 168)])
    if not all(math.isfinite(v) for v in thresholds) or not (24 <= thresholds[0] <= thresholds[1] and 72 <= thresholds[1] <= thresholds[2]):
        raise RuntimeError('정리 보호 시간 설정 오류')
    return {r['worktree']: audit.inspect(r['worktree'], base, r, rows[0]['worktree'],
            copy.deepcopy(state.get(r['worktree'], {'first_seen_at': current, 'last_activity_at': current})),
            current, thresholds) for r in rows}


def board(selected=None, include_cleanup=False):
    snapshot = session_snapshot()  # exactly once, reused across every project
    out = {'at': now(), 'projects': [], 'session_state': snapshot['state'], 'warnings': []}
    all_projects = projects()
    if selected and selected not in all_projects:
        raise RuntimeError('등록되지 않은 프로젝트입니다.')
    for key, (repo, base) in all_projects.items():
        if selected and key != selected:
            continue
        group = {'project': key, 'path': repo, 'tasks': [], 'errors': []}
        out['projects'].append(group)
        try:
            rows = audit.records(repo)
            group['physical_worktrees'] = len(rows)
            try:
                tasks = read_tasks(repo)
            except (RuntimeError, OSError, ValueError, TypeError):
                tasks = []
                group['errors'].append('작업 기록 손상/조회 실패: 미등록으로 표시하며 추정하지 않습니다.')
            try:
                cleanup = cleanup_preview(key, repo, base, rows) if include_cleanup else {}
            except (RuntimeError, OSError, ValueError, TypeError, subprocess.SubprocessError):
                cleanup = {}
                group['errors'].append('정리 판정 unknown: 삭제 불가')
            claimed = set()
            for task in tasks:
                item = copy.deepcopy(task)
                if task.get('related_to'):
                    related = next((t for t in tasks if t['id'] == task['related_to']), None)
                    item['related_goal'] = related['goal'] if related else '관계 기록 미확인'
                item.setdefault('state', '확인필요')
                item.setdefault('next', '기록과 실제 상태를 확인하세요.')
                if task.get('path'):
                    claimed.add(task['path'])
                    try:
                        verify(repo, task)
                        item['identity_state'] = 'verified'
                    except (RuntimeError, OSError, subprocess.SubprocessError):
                        item.update(identity_state='unknown', state='확인필요', next='삭제/교체된 경로와 기록을 확인하세요.')
                group['tasks'].append(item)
            for row in rows:
                if row['worktree'] not in claimed:
                    group['tasks'].append({'id': None, 'goal': '거점' if row is rows[0] else '미등록 작업',
                        'path': row['worktree'], 'branch': row.get('branch'), 'state': '확인필요',
                        'next': '목표를 확인한 뒤 task import로 명시 등록하세요.'})
            for item in group['tasks']:
                path = item.get('path')
                if not path:
                    continue
                item['sessions'] = sessions_at(snapshot, path)
                item['cleanup'] = cleanup.get(path, {'classification': 'UNKNOWN', 'reasons': ['미검사/unknown: 안전 판정이 아닙니다. board --cleanup으로 검사하세요.']})
                item['cleanup_command'] = shlex.join(['awo', 'cleanup', key, '--worktree', path])
                try:
                    item['git_status'] = audit.git(path, 'status', '--porcelain=v1', '--untracked-files=all', '--ignored=matching')
                    item['head'] = audit.git(path, 'rev-parse', 'HEAD')
                except (RuntimeError, OSError, subprocess.SubprocessError):
                    item.update(git_status=None, state='확인필요')
            try:
                group['dispatch_pending'] = pending(repo)
            except (RuntimeError, OSError, ValueError):
                group['errors'].append('실행 소유 기록 unknown: 재실행 금지')
        except (RuntimeError, OSError, ValueError, TypeError, subprocess.SubprocessError):
            group['errors'].append('저장소 조회 error: 경로/접근/Git 상태를 확인하세요.')
    agents = [r for r in snapshot['terminals'] if r.get('connected') is True and r.get('agentIdentity') in ('codex', 'claude')]
    paths = {}
    for row in agents:
        path = str(Path(row['worktreePath']).resolve())
        paths[path] = paths.get(path, 0) + 1
    out['observed_agent_sessions'] = len(agents) if snapshot['state'] == 'known' else None
    out['multiple_agents'] = {p: n for p, n in paths.items() if n > 1}
    if len(agents) > 3:
        out['warnings'].append(f'실제 연결된 작업 세션 {len(agents)}개: 권장 동시 작업 수 3을 넘었습니다 (미등록 포함).')
    for path, count in out['multiple_agents'].items():
        out['warnings'].append(f'같은 경로에 작업자 {count}개: {path} · 파일 중복을 확인하세요.')
    count = sum(t.get('state') == '진행' for p in out['projects'] for t in p['tasks'])
    if count > 3:
        out['warnings'].append(f'진행 {count}개: 권장 동시 작업 수 3을 넘었습니다. 보관은 물리 한도를 늘리지 않습니다.')
    return out


def select(tasks, task_id):
    matches = [t for t in tasks if t['id'] == task_id]
    if len(matches) != 1:
        raise RuntimeError('정확한 stable task ID가 필요합니다.')
    return matches[0]


def bind(repo, tasks, task, path):
    path = str(Path(path).expanduser().resolve())
    branch = validate_worktree(Path(repo), Path(path))
    if task.get('path') and task['path'] != path:
        raise RuntimeError('이미 연결된 작업은 다른 경로로 자동 교체하지 않습니다.')
    if any(t is not task and t.get('path') == path for t in tasks):
        raise RuntimeError('다른 작업에 연결된 경로입니다.')
    if task.get('identity') and (task['identity'] != identity(path) or task['branch'] != 'refs/heads/' + branch):
        raise RuntimeError('기존 identity와 다릅니다. 기록을 덮어쓰지 않습니다.')
    task.update(path=path, branch='refs/heads/' + branch, identity=identity(path))
    event(task, 'bind', path=path)


def handoff(repo, task, action):
    stamp = now()
    entry = {'schema_version': 1, 'at': stamp, 'action': action, 'task': copy.deepcopy(task),
             'continuation': shlex.join(['awo', 'task', 'resume', task['project'], task['id'], '--agent', 'none']),
             'boundary': '작업폴더/dirty/ignored 보존. 자동 삭제·종료·커밋·병합 없음. 독립 워커에서만 구현.'}
    directory = folder(repo) / 'handoffs' / task['id']
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json')
    with target.open('x') as stream:
        json.dump(entry, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    task['handoff'] = str(target)
    return target


def resume_worker(args, repo, task, branch):
    snapshot = session_snapshot()
    evidence = sessions_at(snapshot, task['path'])
    if evidence['state'] == 'unknown':
        raise RuntimeError('세션 목록 미확인: 중복 작업자를 만들지 않습니다.')
    items = evidence['terminals']
    if items:
        if len(items) != 1 or items[0].get('agentIdentity') != args.agent:
            raise RuntimeError('복수/미확인/다른 작업자: 기존 창을 직접 확인하세요.')
        handle = items[0]['handle']
        observed = payload(orca('terminal', 'show', '--terminal', handle)).get('terminal')
        if not isinstance(observed, dict) or not (
                observed.get('handle') == handle and observed.get('worktreePath') == task['path']
                and str(observed.get('branch', '')).removeprefix('refs/heads/') == branch
                and observed.get('connected') is True and observed.get('agentIdentity') == args.agent):
            raise RuntimeError('기존 작업자의 경로/브랜치/연결/identity 검증 실패')
        orca('terminal', 'switch', '--terminal', handle)
        return {'state': 'existing_session_connected', 'path': task['path'], 'branch': branch,
                'terminal_id': handle, 'reason': '검증된 기존 창으로 연결했습니다. 새 턴/프롬프트는 보내지 않았습니다.'}
    validation = task.get('validation', {})
    prompt = (task['goal'] + '\n인계 자료: ' + task.get('handoff', '없음')
              + '\n다음 행동: ' + (task.get('next') or '미기록')
              + '\n검증 결과/출처: ' + json.dumps(validation, ensure_ascii=False))
    launch_args = argparse.Namespace(project=args.project, task=branch.replace('/', '-'),
        agent=args.agent, goal=prompt, worktree=task['path'], new_session=False)
    result, _ = dispatch(launch_args, locked=True)
    return result['awo_dispatch']


def close_candidate(repo, task, input_checked=False):
    branch = verify(repo, task)
    evidence = sessions_at(session_snapshot(), task['path'])
    items = evidence['terminals']
    if evidence['state'] != 'present' or len(items) != 1:
        raise RuntimeError('정확한 단일 작업자 창을 확인할 수 없어 닫지 않습니다.')
    handle = items[0]['handle']
    if handle == os.environ.get('ORCA_TERMINAL_HANDLE'):
        raise RuntimeError('현재 명령을 실행하는 자신의 창은 닫지 않습니다. 거점에서 요청하세요.')
    agent = items[0].get('agentIdentity')
    if agent not in ('codex', 'claude'):
        raise RuntimeError('작업자 identity 미확인: 닫지 않습니다.')
    term = payload(orca('terminal', 'show', '--terminal', handle)).get('terminal', {})
    if not isinstance(term, dict) or not (term.get('handle') == handle and term.get('worktreePath') == task['path']
            and str(term.get('branch', '')).removeprefix('refs/heads/') == branch
            and term.get('connected') is True and term.get('agentIdentity') == agent):
        raise RuntimeError('창 identity 검증 실패: 닫지 않습니다.')
    waited = payload(orca('terminal', 'wait', '--terminal', handle, '--for', 'tui-idle', '--timeout-ms', '1000'))
    if not isinstance(waited.get('wait'), dict) or waited['wait'].get('satisfied') is not True:
        raise RuntimeError('공식 tui-idle 확인 실패: 실행 중/미확인 창을 닫지 않습니다.')
    read = payload(orca('terminal', 'read', '--terminal', handle, '--screen', '--limit', '400'))
    screen = read.get('terminal', read)
    if not isinstance(screen, dict) or screen.get('handle') != handle or screen.get('source') != 'screen' or screen.get('truncated') is not False or screen.get('limited') is not False or not isinstance(screen.get('tail'), list) or not screen['tail'] or any(not isinstance(line, str) for line in screen['tail']):
        raise RuntimeError('화면/미전송 입력 보존 확인 실패: 닫지 않습니다.')
    if ('draft' in screen and screen['draft'] != '') or ('draft' not in screen and not input_checked):
        raise RuntimeError('빈 draft 증거가 없습니다. draft 없는 버전은 실제 화면 확인 후 --input-checked가 필요합니다.')
    # Keep screen content out of receipts/handoffs (may contain secrets).
    import hashlib
    fingerprint = hashlib.sha256(json.dumps(screen['tail']).encode()).hexdigest()
    return {'terminal_id': handle, 'agent': agent, 'screen_fingerprint': fingerprint}


def park_close(args, repo, file, tasks, task):
    if not args.next or not args.validation or not args.processes_checked:
        raise RuntimeError('--close는 --next, --validation, --processes-checked가 필요합니다.')
    if pending(repo):
        raise RuntimeError('생성 결과 미확인: 창을 닫지 않습니다.')
    candidate = close_candidate(repo, task, args.input_checked)
    task['close'] = dict(candidate, state='prepared', at=now(), input_checked=args.input_checked)
    event(task, 'close-prepared')
    handoff(repo, task, 'park-close')
    audit.save(file, tasks)  # no close before durable handoff AND task record
    fresh = close_candidate(repo, task, args.input_checked)
    if fresh != candidate:
        raise RuntimeError('재검증 중 창/화면이 바뀌었습니다. 닫지 않습니다.')
    task['close']['state'] = 'attempting'
    audit.save(file, tasks)
    try:
        orca('terminal', 'close', '--terminal', candidate['terminal_id'])
        after = sessions_at(session_snapshot(), task['path'])
        task['close']['state'] = 'closed' if after['state'] == 'absent' else 'unverified'
        task['state'] = '보관' if after['state'] == 'absent' else '확인필요'
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        task['close']['state'] = 'unverified'
        task['state'] = '확인필요'
    event(task, 'close-result', result=task['close']['state'])
    handoff(repo, task, 'park-close-result')


def task_command(args):
    known = projects()
    if args.project not in known:
        raise RuntimeError('등록되지 않은 프로젝트입니다.')
    repo, _ = known[args.project]
    file = folder(repo) / 'tasks.json'
    if args.action == 'show':
        tasks = read_tasks(repo)
        return select(tasks, args.id) if args.id else tasks
    with project_lock(repo), task_lock(file):
        tasks = read_tasks(repo)
        if args.action in ('add', 'import'):
            if not args.goal.strip():
                raise RuntimeError('구체적인 목표가 필요합니다.')
            task = event({'project': args.project, 'goal': args.goal.strip(), 'path': None,
                          'branch': None, 'identity': None, 'state': '할일', 'next': args.next or ''}, 'add')
            tasks.append(task)
            if args.related_to:
                related = select(tasks, args.related_to)
                if related is task:
                    raise RuntimeError('자기 자신을 관련 작업으로 지정할 수 없습니다.')
                task['related_to'] = related['id']
                event(task, 'relate', related_to=related['id'])
            if args.action == 'import':
                bind(repo, tasks, task, args.worktree)
        else:
            task = select(tasks, args.id)
            task.setdefault('project', args.project)
        if args.action == 'bind':
            bind(repo, tasks, task, args.worktree)
        if args.action in ('park', 'done'):
            if task.get('path'):
                verify(repo, task)
            task['next'] = args.next or task.get('next', '')
            task['validation'] = {'result': args.validation or '미검증', 'source': '사용자 제공', 'at': now()}
            snapshot = session_snapshot()
            evidence = sessions_at(snapshot, task['path']) if task.get('path') else {'state': 'absent'}
            # Terminal absence alone cannot establish absence of shell-launched servers.
            certain = evidence['state'] == 'absent' and args.processes_checked and not pending(repo)
            task['state'] = ('보관' if args.action == 'park' else '완료') if certain else '확인필요'
            task['process_evidence'] = {'sessions': evidence, 'user_checked': args.processes_checked, 'at': now()}
            event(task, args.action, result=task['state'])
            handoff(repo, task, args.action)
            if args.action == 'park' and args.close:
                audit.save(file, tasks)
                park_close(args, repo, file, tasks, task)
        if args.action == 'start' and not task.get('path'):
            if pending(repo):
                raise RuntimeError('이전 생성 결과 미확인: 재실행 차단')
            prompt = (task['goal'] + '\n인계 자료: ' + task.get('handoff', '없음')
                      + '\n다음 행동: ' + (task.get('next') or '미기록')
                      + '\n검증 결과/출처: ' + json.dumps(task.get('validation', {}), ensure_ascii=False))
            launch_args = argparse.Namespace(project=args.project, task=task['id'].lower(),
                agent=args.agent, goal=prompt, worktree=None, new_session=False)
            result, code = dispatch(launch_args, locked=True)
            task['dispatch'] = result['awo_dispatch']
            path = task['dispatch'].get('path')
            if path:
                bind(repo, tasks, task, path)
            task['state'] = '진행' if not code and task['dispatch']['state'] == 'session_confirmed' else '확인필요'
            event(task, 'start', dispatch=task['dispatch'])
        elif args.action in ('start', 'resume'):
            branch = verify(repo, task)
            if pending(repo):
                raise RuntimeError('중단된 실행이 미확인입니다. task reconcile이 필요합니다.')
            if args.agent == 'none':
                task['dispatch'] = {'state': 'worktree_only', 'path': task['path'],
                                    'reason': '경로 선택 완료. 독립 워커 연결/턴 시작은 확인하지 않았습니다.'}
            else:
                task['dispatch'] = resume_worker(args, repo, task, branch)
            task['state'] = '진행' if task['dispatch']['state'] in ('session_confirmed', 'idle', 'existing_session_connected') else '확인필요'
            event(task, 'resume', dispatch=task['dispatch'])
        if args.action == 'reconcile':
            verify(repo, task)
            intent = pending(repo)
            if not intent:
                raise RuntimeError('미확인 실행 기록이 없습니다.')
            if intent.get('path') and intent['path'] != task['path']:
                raise RuntimeError('미확인 실행과 경로가 다릅니다.')
            if intent.get('goal') and intent['goal'].split('\n인계 자료:')[0] != task['goal']:
                raise RuntimeError('미확인 실행과 목표가 다릅니다.')
            evidence = sessions_at(session_snapshot(), task['path'])
            if evidence['state'] == 'unknown' or not args.processes_checked:
                raise RuntimeError('완전한 세션 목록과 사용자의 프로세스 확인이 필요합니다.')
            # Reconciliation acknowledges an outcome, never launches or terminates.
            intent.update(state='reconciled', registration_pending=False, at=now(), task_id=task['id'], path=task['path'], evidence=evidence)
            audit.save(folder(repo) / 'dispatch.json', intent)
            event(task, 'reconcile', evidence=evidence)
        audit.save(file, tasks)
        if args.action in ('start', 'resume'):
            acknowledge(repo)
        return task


def resource_file():
    return projects_file().resolve().parent / '.awo-resources.json'


def read_resources(file):
    data = json.loads(file.read_text()) if file.exists() else {'schema_version': 1, 'resources': []}
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('resources'), list):
        raise RuntimeError('자원 기록 손상: 충돌 여부를 확인할 수 없습니다.')
    for r in data['resources']:
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k] for k in ('project', 'task_id', 'kind', 'value')) or r['kind'] not in ('port', 'output', 'db'):
            raise RuntimeError('자원 항목 손상: 등록 차단')
    return data


def resource_value(kind, value):
    if kind == 'port':
        number = int(value)
        if not 1 <= number <= 65535:
            raise RuntimeError('포트 범위는 1..65535입니다.')
        return str(number)
    if kind == 'output':
        return str(Path(value).expanduser().resolve())
    if not value.strip():
        raise RuntimeError('DB namespace를 명시하세요 (예: server/database/schema).')
    return value.strip()


def conflicts(kind, value, rows):
    def match(r):
        if r['kind'] != kind:
            return False
        if kind != 'output':
            return r['value'] == value
        a, b = Path(value), Path(r['value'])
        return a == b or a in b.parents or b in a.parents
    return [r for r in rows if match(r)]


def port_available(value):
    try:
        with socket.socket() as sock:
            sock.bind(('0.0.0.0', int(value)))
        if socket.has_ipv6:
            with socket.socket(socket.AF_INET6) as sock:
                sock.bind(('::', int(value)))
        return True
    except OSError:
        return False


def resource_command(args):
    file = resource_file()
    if args.action == 'list':
        return read_resources(file)
    value = resource_value(args.kind, args.value)
    if args.action in ('check', 'suggest'):
        rows = read_resources(file)['resources']
        if args.action == 'suggest':
            if args.kind != 'port':
                raise RuntimeError('suggest는 port만 지원합니다.')
            candidates = (str(p) for p in range(int(value), min(65536, int(value) + 1000)))
            value = next((p for p in candidates if not conflicts('port', p, rows) and port_available(p)), None)
            if value is None:
                raise RuntimeError('사용 가능한 포트 제안이 없습니다.')
        return {'kind': args.kind, 'value': value, 'conflicts': conflicts(args.kind, value, rows),
                'available_now': port_available(value) if args.kind == 'port' else None,
                'notice': '예약/격리 보장이 아닙니다. 실행 직전에 다시 확인하세요.'}
    # One global lock across all projects sharing this config, then the project lock.
    with task_lock(file):
        repo, _ = projects()[args.project]
        with project_lock(repo):
            task = select(read_tasks(repo), args.id)
            data = read_resources(file)
            if args.action == 'release':
                data['resources'] = [r for r in data['resources'] if not (
                    r['project'] == args.project and r['task_id'] == args.id and r['kind'] == args.kind and r['value'] == value)]
            else:
                same = [r for r in data['resources'] if r['project'] == args.project and r['task_id'] == task['id'] and r['kind'] == args.kind and r['value'] == value]
                if not same and conflicts(args.kind, value, data['resources']):
                    raise RuntimeError('다른 등록 자원과 충돌합니다. 기존 자원은 변경하지 않습니다.')
                if args.kind == 'port' and not same and not port_available(value):
                    raise RuntimeError('이미 사용 중이거나 확인할 수 없는 포트입니다.')
                if not same:
                    data['resources'].append({'project': args.project, 'task_id': task['id'], 'kind': args.kind, 'value': value, 'at': now()})
            data.setdefault('events', []).append({'action': args.action, 'project': args.project, 'task_id': args.id, 'kind': args.kind, 'value': value, 'at': now()})
            audit.save(file, data)
            return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('board', help='전체 작업판 (읽기 전용)')
    b.add_argument('--project')
    b.add_argument('--details', action='store_true', help='긴 ID·경로·정리 안내도 표시')
    b.add_argument('--json', action='store_true')
    b.add_argument('--cleanup', action='store_true', help='기존 audit 안전 판정도 상세 조회 (느릴 수 있음)')
    t = sub.add_parser('task', help='작업 기록과 인계')
    ts = t.add_subparsers(dest='action', required=True)
    for name in ('add', 'import', 'show', 'bind', 'park', 'start', 'resume', 'done', 'reconcile'):
        p = ts.add_parser(name)
        p.add_argument('project')
        if name in ('add', 'import'):
            p.add_argument('goal')
            p.add_argument('--related-to', help='같은 프로젝트의 관련 stable ID (Git parent 아님)')
        else:
            p.add_argument('id', nargs='?' if name == 'show' else None)
        if name in ('import', 'bind'):
            p.add_argument('--worktree', required=True)
        if name in ('add', 'import', 'park', 'done'):
            p.add_argument('--next')
        if name in ('park', 'done'):
            p.add_argument('--validation')
        if name in ('park', 'done', 'reconcile'):
            p.add_argument('--processes-checked', action='store_true', help='사용자가 관련 프로세스 상태를 별도로 확인했음')
        if name == 'park':
            p.add_argument('--close', action='store_true', help='명시 승인된 단일 idle 창만 인계 후 닫음')
            p.add_argument('--input-checked', action='store_true', help='draft 필드 없는 버전: 호출자가 실제 화면의 미전송 입력 부재를 확인했음')
        if name == 'start':
            p.add_argument('--agent', choices=['codex', 'claude'], required=True)
        if name == 'resume':
            p.add_argument('--agent', choices=['none', 'codex', 'claude'], default='none')
        p.add_argument('--json', action='store_true')
    r = sub.add_parser('resource', help='명시적 실행 자원 등록 (프로세스 변경 없음)')
    rs = r.add_subparsers(dest='action', required=True)
    for name in ('list', 'register', 'release', 'check', 'suggest'):
        p = rs.add_parser(name)
        if name in ('register', 'release'):
            p.add_argument('project')
            p.add_argument('id')
        if name != 'list':
            p.add_argument('kind', choices=['port', 'output', 'db'])
            p.add_argument('value')
        p.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = board(args.project, args.cleanup) if args.command == 'board' else task_command(args) if args.command == 'task' else resource_command(args)
        if args.command == 'board' and not args.json:
            from awo_board import render_board
            from shutil import get_terminal_size
            print(render_board(result, details=args.details, width=get_terminal_size((80, 24)).columns))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print('확인필요: ' + (str(exc) if isinstance(exc, RuntimeError) else '조회/저장 실패. 상태를 확인한 뒤 다시 실행하세요.'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
