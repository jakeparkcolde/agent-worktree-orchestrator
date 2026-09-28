"""Pure text presentation of the existing board JSON; no inventory or writes."""
from pathlib import PurePath
import unicodedata

GROUPS = ('열린 작업', '이어갈 작업', '아이디어', '보관·완료', '확인할 연결', '지시 거점')
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
    if row.get('state') in ('보관', '완료'):
        return '보관·완료'
    return '이어갈 작업' if row.get('path') else '아이디어'


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)


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
        for project, row in items:
            if name == '지시 거점' and not details:
                session = row.get('sessions', {})
                count = f"연결 agent {len(connected(row))} / 창 {len(session.get('terminals', []))}" if session.get('state') in ('present', 'absent') else '세션 미확인'
                add(f"{project['project']} · {count}", '  - ', '    ')
                continue
            registered = bool(row.get('id'))
            label = row.get('goal') or '목표 미기록'
            if not registered:
                label = ('거점' if name == '지시 거점' else '미등록 작업') + ' · ' + PurePath(row.get('path') or '').name
            badges = []
            if row.get('identity_state') == 'unknown':
                badges.append('폴더 연결 검증 실패')
            if row.get('path'):
                ses = row.get('sessions', {})
                if ses.get('state', 'unknown') == 'unknown':
                    badges.append('세션 조회 미확인')
                elif ses.get('state') == 'present':
                    badges.append(f"연결 agent {len(connected(row))} / 창 {len(ses.get('terminals', []))}")
                    if name == '확인할 연결':
                        badges.append('작업자 연결 확인 필요')
                elif details or name != '이어갈 작업':
                    badges.append('연결된 창 없음')
            if registered:
                state = row.get('state')
                if state not in (None, '확인필요'):
                    badges.append(str(state))
                elif details:
                    badges.append('상태 미기록/확인필요 기록')
            add(f"{project['project']} · {label}", '  - ', '    ')
            if badges:
                add(' · '.join(badges), '    ')
            if row.get('related_to'):
                add('관련 목표: ' + row.get('related_goal', '관계 기록 미확인'), '    ')
            if name != '지시 거점' and (details or row.get('next') and row['next'] not in AUTO_NEXT):
                next_action = row.get('next') or ('목표 확인 후 task import로 등록' if not registered else '다음 행동 미기록')
                add('다음: ' + next_action, '    ')
            if details:
                if name == '지시 거점' and row.get('next'):
                    add('다음: ' + row['next'], '    ')
                add('ID: ' + (row.get('id') or '미등록'), '    ')
                add('경로: ' + (row.get('path') or '작업폴더 없음'), '    ')
                add('브랜치: ' + (row.get('branch') or '미연결'), '    ')
                if row.get('related_to'):
                    add('관련 ID: ' + row['related_to'], '    ')
                if row.get('path'):
                    add('정리: ' + CLEANUP_LABELS.get(row.get('cleanup', {}).get('classification'), '미확인'), '    ')
                    if row.get('cleanup_command'):
                        add(row['cleanup_command'], '    ')
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
    return '\n'.join(lines)
