"""Local planning and contextual suggestions. No I/O or execution decisions."""
from datetime import date
import hashlib
import json
import re
import unicodedata


def valid_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('예정일은 KST YYYY-MM-DD 형식이어야 합니다.')
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('실제로 존재하는 날짜를 입력하세요.') from exc
    return value


def validate_planning(planning):
    if not isinstance(planning, dict):
        raise ValueError('planning은 객체여야 합니다.')
    if 'later' in planning and not isinstance(planning['later'], bool):
        raise ValueError('later는 boolean이어야 합니다.')
    if 'scheduled_for' in planning:
        valid_date(planning['scheduled_for'])
        if planning.get('timezone') != 'Asia/Seoul':
            raise ValueError('예정일의 시간대는 Asia/Seoul이어야 합니다.')


def planning_requested(args):
    return any((getattr(args, 'later', False), getattr(args, 'clear_later', False),
                getattr(args, 'date', None) is not None, getattr(args, 'clear_date', False),
                getattr(args, 'next', None) is not None, getattr(args, 'clear_next', False)))


def update_planning(task, args):
    """Mutate only selected planning fields and the existing compatible next field."""
    planning = dict(task.get('planning', {}))
    validate_planning(planning)
    if getattr(args, 'later', False):
        planning['later'] = True
    if getattr(args, 'clear_later', False):
        planning.pop('later', None)
    if getattr(args, 'date', None) is not None:
        planning.update(scheduled_for=valid_date(args.date), timezone='Asia/Seoul')
    if getattr(args, 'clear_date', False):
        planning.pop('scheduled_for', None)
        planning.pop('timezone', None)
    if planning or 'planning' in task:
        task['planning'] = planning
    if getattr(args, 'next', None) is not None:
        task['next'] = args.next
    if getattr(args, 'clear_next', False):
        task['next'] = ''


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def recommend(tasks, goal, current_id=None, intent='auto', context=''):
    if not goal.strip():
        raise RuntimeError('구체적인 목표가 필요합니다.')
    if intent not in ('auto', 'reuse', 'separate', 'later'):
        raise RuntimeError('지원하지 않는 의도입니다.')
    current = next((t for t in tasks if t['id'] == current_id), None)
    if current_id and current is None:
        raise RuntimeError('현재 작업은 같은 프로젝트의 정확한 ID여야 합니다.')
    matches = [t for t in tasks if normalized(t['goal']) == normalized(goal)]
    decision = intent
    reasons = []
    if intent != 'auto':
        reasons.append('사용자가 명시한 의도를 우선했습니다.')
    else:
        cues = []
        # Narrow explicit phrases; a vague mention or semantic similarity is not permission.
        for name, patterns in (
                ('later', ('나중에', '아이디어로 저장', '할일로 저장')),
                ('separate', ('따로 열어', '별도로 열어', '별도 작업', '새 주제로')),
                ('reuse', ('계속 고치', '이거 더 고치', '이어 하', '이어서', '돌아가'))):
            if any(pattern in context for pattern in patterns):
                cues.append(name)
        uncertain = any(word in context for word in ('말고', '하지 마', '아니', '않', '할까', '어떨까', '?'))
        if len(cues) == 1 and not uncertain:
            decision = cues[0]
            reasons.append('제공한 문맥의 명시적 요청 표현을 사용했습니다.')
        else:
            decision = 'needs-choice'
            reasons.append('명시적 의도가 없거나 서로 충돌합니다. 유사도/같은 문구만으로 재사용하지 않습니다.')
    target = current
    if decision == 'reuse' and intent == 'auto' and current and normalized(current['goal']) != normalized(goal):
        decision = 'needs-choice'
        reasons.append('현재 작업과 입력 목표가 다릅니다. 현재 ID만으로 자동 재사용하지 않습니다.')
    if decision == 'reuse' and target is None:
        decision = 'needs-choice'
        reasons.append('재사용할 정확한 기존 작업 ID를 확인하세요.')
    if current:
        reasons.append('현재 작업 문맥: ' + current['goal'])
    if decision == 'separate':
        reasons.append('관련된 독립 아이디어로 저장합니다. 기존 변경·대화는 복사하지 않으며 Git parent 관계가 아닙니다.')
    if decision == 'later':
        reasons.append('나중에 검토할 아이디어만 저장합니다. 폴더/창을 만들지 않습니다.')
    return {'recommendation': decision, 'goal': goal.strip(), 'reasons': reasons,
            'current_task': current_id, 'target_id': target['id'] if decision == 'reuse' else None,
            'related_to': current_id if decision in ('separate', 'later') else None,
            'candidates': [{'id': t['id'], 'goal': t['goal']} for t in matches],
            'heuristic': intent == 'auto',
            'mode': 'PREVIEW', 'notice': '자동 문맥 추천은 휴리스틱 후보입니다. 저장은 확인한 --intent와 --apply, 폴더/창 시작은 task start로 별도 요청하세요.'}


def idea_request(args):
    """Stable retry key; a different explicit request ID authorizes another card."""
    payload = {'goal': args.goal.strip(), 'current_task': args.current_task, 'intent': args.intent,
               'later': args.later, 'clear_later': args.clear_later, 'date': args.date,
               'clear_date': args.clear_date, 'next': args.next, 'clear_next': args.clear_next}
    request_id = args.request_id
    if request_id is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', request_id):
        raise RuntimeError('request-id는 영문/숫자로 시작하는 80자 이하 식별자여야 합니다.')
    key = request_id or hashlib.sha256(json.dumps(
        [normalized(args.goal), args.current_task, args.intent], ensure_ascii=False).encode()).hexdigest()
    return {'key': ('explicit:' if request_id else 'default:') + key, 'payload': payload}
