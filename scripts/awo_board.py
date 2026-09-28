"""Pure text presentation of the existing board JSON; no inventory or writes."""
from pathlib import PurePath
import unicodedata

GROUPS = ('예정', '열린 작업', '이어갈 작업', '아이디어', '나중에', '완료', '확인할 연결', '지시 거점')
AUTO_NEXT = {'기록과 실제 상태를 확인하세요.', '목표를 확인한 뒤 task import로 명시 등록하세요.',
             '삭제/교체된 경로와 기록을 확인하세요.'}
SESSION_LABELS = {'present': '기존 창 있음', 'absent': '등록된 창 없음', 'unknown': '미확인'}
CLEANUP_LABELS = {'UNKNOWN': '미검사 (안전 판정 아님)', 'BLOCKED': '정리 불가',
    'SAFE_CLEANUP': '정리 후보 (적용 시 재검사)', 'ACTIVE': '최근 작업', 'ACTIVE_IDLE': '최근 활동 보호',
    'ARCHIVE': '산출물 보존 필요', 'REVIEW': '수동 검토', 'SYNCED': '동등 내용 확인 필요',
    'STALE': '장기 미활동 검토', 'MERGE': '미병합 변경 보존'}


def connected(row):
    return [t for t in row.get('sessions', {}).get('terminals', [])
            if t.get('connected') is True and t.get('agentIdentity') in ('codex', 'claude')]


def section(row):
    if not row.get('id') and row.get('goal') == '거점':
        return '지시 거점'
    recorded_state = row.get('recorded_state', row.get('state'))
    if recorded_state == '완료':
        return '완료'
    planning = row.get('planning', {})
    if planning.get('scheduled_for'):
        return '예정'
    if planning.get('later') or recorded_state == '보관':
        return '나중에'
    if row.get('identity_state') == 'unknown' or ('git_status' in row and row['git_status'] is None):
        return '확인할 연결'
    if row.get('path'):
        session = row.get('sessions', {})
        terms = session.get('terminals', [])
        if session.get('state', 'unknown') == 'unknown':
            return '확인할 연결'
        if session.get('state') == 'present' and (len(terms) != 1 or len(connected(row)) != 1):
            return '확인할 연결'
        if connected(row):
            return '열린 작업'
    return '이어갈 작업' if row.get('path') else '아이디어'


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)


def board_advice(report):
    """At most three evidence/action pairs, in safety-first order; never act."""
    projects = report.get('projects', [])
    suggestions = []

    def suggest(scope, evidence, action):
        suggestions.append({'scope': scope, 'evidence': evidence, 'action': action})

    known = report.get('session_state') == 'known'
    checks = []
    for project in projects:
        problems = []
        if project.get('errors'):
            problems.append(f"조회 오류 {len(project['errors'])}건")
        if project.get('dispatch_pending'):
            problems.append('이전 실행 결과 미확인')
        if any('git_status' in r and r['git_status'] is None and r.get('identity_state') != 'unknown'
               for r in project.get('tasks', [])):
            problems.append('일부 Git 상태 조회 실패')
        if known and any(r.get('path') and r.get('sessions', {}).get('state', 'unknown') == 'unknown'
                         for r in project.get('tasks', [])):
            problems.append('일부 세션 조회 미확인')
        if problems:
            checks.append(f"{project['project']}: {' · '.join(problems)}")
    if checks or not known:
        evidence = '' if known else '전체 환경 세션 조회 미확인: 연결 수·복수 작업자 여부를 판단할 수 없습니다. '
        if checks:
            evidence += f'조회 범위 {len(checks)}개 프로젝트 확인: ' + ' / '.join(checks[:3])
            if len(checks) > 3:
                evidence += f' / 외 {len(checks) - 3}개 프로젝트'
        scope = '조회 범위' if known else '전체 환경 · 조회 범위' if checks else '전체 환경'
        action = '--details로 실패 원인과 기존 실행을 확인하세요. 재실행 전 연결 상태를 확인하세요.'
        if not known:
            action += ' Orca 목록 조회를 먼저 확인하고 연결 수에 따른 보관 판단은 보류하세요.'
        suggest(scope, evidence.strip(), action)

    if known:
        by_path = {}
        multiple = dict(report.get('multiple_agents', {}))
        for project in projects:
            for row in project.get('tasks', []):
                if row.get('path'):
                    by_path.setdefault(row['path'], project['project'])
                    handles = {t.get('handle') for t in connected(row) if t.get('handle')}
                    if len(handles) > 1:
                        multiple.setdefault(row['path'], len(handles))
        entries = sorted(((path, count) for path, count in multiple.items()
                          if isinstance(count, int) and count >= 2), key=lambda item: (-item[1], item[0]))
        if entries:
            outside = sum(path not in by_path for path, _ in entries)
            scope = ('조회 범위' if not outside else '전체 환경 · 조회 범위 밖 (프로젝트 미확인)'
                     if outside == len(entries) else '전체 환경 · 조회 범위 안팎')
            examples = ' · '.join(f"{by_path.get(path, '범위 밖 프로젝트 미확인')} {count}개"
                                  for path, count in entries[:3])
            if len(entries) > 3:
                examples += f' · 외 {len(entries) - 3}곳'
            suggest(scope, f'같은 폴더에 복수 작업자 연결 {len(entries)}곳: {examples}.',
                    '각 창의 목표와 수정 파일 중복을 확인하고 담당을 구분하세요. 연결은 실행 여부의 증거가 아닙니다.')

    failures = []
    for project in projects:
        count = sum(r.get('identity_state') == 'unknown' for r in project.get('tasks', []))
        if count:
            failures.append((project['project'], count))
    if failures:
        failures.sort(key=lambda item: (-item[1], item[0]))
        examples = ' · '.join(f'{name} {count}개' for name, count in failures[:3])
        if len(failures) > 3:
            examples += f' · 외 {len(failures) - 3}개 프로젝트'
        suggest('조회 범위', f'작업폴더 연결 검증 실패 {sum(count for _, count in failures)}개: {examples}.',
                '--details의 경로·브랜치를 실제 폴더와 대조하세요. 기존 ID를 다른 폴더에 자동 연결하지 마세요.')
    total = report.get('observed_agent_sessions')
    if known and isinstance(total, int) and total > 3:
        suggest('전체 환경', f'연결된 작업자 {total}개로 권장 수 3을 넘습니다.',
                '오늘 집중할 작업 1개를 직접 고르세요. 나머지는 다음 행동을 기록한 뒤 보관을 검토하되 안전 조건은 별도로 확인하세요.')
    for project in projects:
        rows = project.get('tasks', [])
        count = sum(known and section(r) == '열린 작업' and (not (r.get('next') or '').strip() or r.get('next') in AUTO_NEXT)
                    for r in rows)
        if count:
            suggest(project['project'], f'연결된 창이 있는 작업 {count}개에 사용자가 기록한 다음 행동이 없습니다.',
                    '각 작업에서 다음에 할 일을 한 줄씩 기록하세요.')
    for project in projects:
        count = sum(not r.get('id') and section(r) != '지시 거점' for r in project.get('tasks', []))
        if count:
            suggest(project['project'], f'목표가 미등록인 작업폴더 {count}개.',
                    '실제 목표를 확인한 뒤 task import로 등록하세요. 폴더명만으로 목표를 정하지 마세요.')
    return suggestions[:3]


def wrap(text, width, indent='', continuation=None):
    """Wrap even long Korean words by terminal cells, without external packages."""
    continuation = indent if continuation is None else continuation
    lines = []
    line = indent
    for char in str(text).replace('\t', '    '):
        if char == '\n':
            lines.append(line.rstrip())
            line = continuation
        elif cell_width(line + char) > width:
            lines.append(line.rstrip())
            line = continuation + char.lstrip()
        else:
            line += char
    lines.append(line.rstrip())
    return lines


def render_board(report, details=False, width=80):
    width = max(20, width)
    lines = []
    def add(text='', indent='', continuation=None):
        lines.extend(wrap(text, width, indent, continuation))
    projects = report.get('projects', [])
    folders = sum(p.get('physical_worktrees', 0) for p in projects)
    incomplete = any('physical_worktrees' not in p for p in projects)
    agents = set()
    for project in projects:
        for row in project.get('tasks', []):
            for i, term in enumerate(connected(row)):
                agents.add(term.get('handle') or (row.get('path'), i))
    sessions_known = report.get('session_state') == 'known' and all(
        not r.get('path') or r.get('sessions', {}).get('state', 'unknown') != 'unknown'
        for p in projects for r in p.get('tasks', []))
    scoped = str(len(agents)) if sessions_known else '미확인'
    total = report.get('observed_agent_sessions')
    add(f"조회 범위 · 프로젝트 {len(projects)}개 · 실제 폴더 {folders}개" + (' (일부 미확인)' if incomplete else '') + f' · 연결된 agent {scoped}개')
    add(f"전체 환경 · 연결된 agent {total if total is not None else '미확인'}개 (프로젝트 필터 밖 포함)")
    add('창 연결은 실행 중이라는 뜻이 아닙니다. 정리 안전성은 별도 검사합니다.')
    if total is not None and total > 3:
        add('전체 환경 안내 · 연결된 agent가 권장 동시 작업 수 3을 넘습니다.')
    multiple = report.get('multiple_agents', {})
    if multiple:
        add(f'전체 환경 안내 · {len(multiple)}개 폴더에 복수 agent 연결: 파일 중복을 확인하세요.')
    recorded = sum(r.get('state') == '진행' for p in projects for r in p.get('tasks', []))
    if recorded > 3 and (total is None or total <= 3):
        add(f'조회 범위 안내 · 진행 기록 {recorded}개: 실제 실행 여부와 별개입니다.')
    if details:
        for warning in dict.fromkeys(report.get('warnings', [])):
            add('전체 환경/조회 기록 안내 · ' + warning)
    for name in GROUPS:
        items = [(p, r) for p in projects for r in p.get('tasks', []) if section(r) == name]
        if not items:
            continue
        add()
        add(f'{name} ({len(items)})')
        if not details and name != '지시 거점':
            hints = []
            if any(r.get('id') and r.get('state') in (None, '확인필요') for _, r in items):
                hints.append('상태 미기록/확인필요 기록은 실제 연결 오류와 구분합니다.')
            if any(r.get('next') in AUTO_NEXT or not r.get('id') for _, r in items):
                hints.append('폴더·세션 연결을 확인하세요.' if name == '확인할 연결' else '미등록 목표와 기록은 확인 후 등록·갱신하세요.')
            if hints:
                add(' '.join(hints), '  ')
        previous_project = None
        project_keys = list(dict.fromkeys(p['project'] for p, _ in items))
        if name == '지시 거점':
            add('프로젝트 | 연결 작업자 | 창', '  ')
            add('---------|-------------|---', '  ')
        for index, (project, row) in enumerate(items):
            if name == '지시 거점':
                session = row.get('sessions', {})
                count = f"{len(connected(row))} | {len(session.get('terminals', []))}" if session.get('state') in ('present', 'absent') else '미확인 | 미확인'
                add(f"{project['project']} | {count}", '  ')
                if details:
                    for title, value in [('ID', row.get('id') or '미등록'), ('경로', row.get('path')),
                                         ('브랜치', row.get('branch')), ('다음', row.get('next')),
                                         ('정리', row.get('cleanup_command'))]:
                        if value:
                            add(f'{title}: {value}', '    ')
                continue
            if previous_project != project['project']:
                project_count = sum(p['project'] == project['project'] for p, _ in items)
                last_project = project['project'] == project_keys[-1]
                project_stem = '     ' if last_project else '  │  '
                add(f"{project['project']} ({project_count})", '  └─ ' if last_project else '  ├─ ', project_stem)
                previous_project = project['project']
            last_task = index + 1 == len(items) or items[index + 1][0]['project'] != project['project']
            task_prefix = project_stem + ('└─ ' if last_task else '├─ ')
            body_prefix = project_stem + ('   ' if last_task else '│  ')
            registered = bool(row.get('id'))
            label = row.get('goal') or '목표 미기록'
            if not registered:
                label = ('거점' if name == '지시 거점' else '미등록 작업') + ' · ' + PurePath(row.get('path') or '').name
            badges = []
            planning = row.get('planning', {})
            if planning.get('scheduled_for'):
                badges.append('예정일 ' + planning['scheduled_for'] + ' (KST)')
            if not row.get('path'):
                badges.append('아이디어 카드 · 폴더 없음')
            if row.get('identity_state') == 'unknown':
                badges.append('폴더 연결 검증 실패')
            elif 'git_status' in row and row['git_status'] is None:
                badges.append('Git 상태 조회 미확인')
            if row.get('path'):
                ses = row.get('sessions', {})
                if ses.get('state', 'unknown') == 'unknown':
                    badges.append('세션 조회 미확인')
                elif ses.get('state') == 'present':
                    badges.append(f"연결 agent {len(connected(row))} / 창 {len(ses.get('terminals', []))}")
                    if len(ses.get('terminals', [])) != 1 or len(connected(row)) != 1:
                        badges.append('작업자 연결 확인 필요')
                elif details or name != '이어갈 작업':
                    badges.append('연결된 창 없음')
            if registered:
                state = row.get('state')
                if state not in (None, '확인필요'):
                    badges.append(str(state))
                elif details:
                    badges.append('상태 미기록/확인필요 기록')
            add(label, task_prefix, body_prefix)
            if badges:
                add(' · '.join(badges), body_prefix)
            if row.get('related_to'):
                add('관련 목표: ' + row.get('related_goal', '관계 기록 미확인'), body_prefix)
            if name != '지시 거점' and (details or row.get('next') and row['next'] not in AUTO_NEXT):
                next_action = row.get('next') or ('목표 확인 후 task import로 등록' if not registered else '다음 행동 미기록')
                add('다음: ' + next_action, body_prefix)
            if details:
                if name == '지시 거점' and row.get('next'):
                    add('다음: ' + row['next'], '    ')
                add('ID: ' + (row.get('id') or '미등록'), body_prefix)
                add('경로: ' + (row.get('path') or '작업폴더 없음'), body_prefix)
                add('브랜치: ' + (row.get('branch') or '미연결'), body_prefix)
                if row.get('related_to'):
                    add('관련 ID: ' + row['related_to'], body_prefix)
                if row.get('path'):
                    add('정리: ' + CLEANUP_LABELS.get(row.get('cleanup', {}).get('classification'), '미확인'), body_prefix)
                    if row.get('cleanup_command'):
                        add(row['cleanup_command'], body_prefix)
    for project in projects:
        problems = list(dict.fromkeys(project.get('errors', [])))
        if project.get('dispatch_pending'):
            problems.append('중단된 실행 미확인: 재실행 차단, task reconcile 필요')
        if problems:
            add()
            add(f"{project['project']} · 확인할 기록")
            for problem in problems:
                add(problem, '  - ', '    ')
    if not details:
        add()
        add('상세 ID·경로: --details · 기본 정리 미검사 (안전 판정 아님) · 정리 검사: --cleanup --details')
    advice = board_advice(report)
    if advice:
        add()
        add('지금 할 만한 일')
        for item in advice:
            add(f"{item['scope']} · {item['evidence']}", '  - ', '    ')
            add(item['action'], '    ')
    return '\n'.join(lines)
