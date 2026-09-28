"""Pure presentation tests: no Git, Orca, config or filesystem mutation."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from awo_board import board_advice, cell_width, render_board, section
import awo_lifecycle


def task(**extra):
    return dict({'id': 'task-long-stable-identifier', 'goal': '알림 누락 수정',
                 'path': '/repo/work/alerts', 'state': '확인필요', 'identity_state': 'verified',
                 'sessions': {'state': 'absent', 'terminals': []}, 'next': '실패 재현',
                 'cleanup_command': 'awo cleanup app --worktree /repo/work/alerts'}, **extra)


def report(*rows):
    return {'projects': [{'project': 'app', 'path': '/repo', 'physical_worktrees': 2,
                          'tasks': list(rows), 'errors': []}], 'session_state': 'known',
            'observed_agent_sessions': 7, 'multiple_agents': {}, 'warnings': []}


class BoardRendererTests(unittest.TestCase):
    def test_tree_siblings_continuations_and_primary_table(self):
        source = report(task(goal='첫 작업'), task(goal='둘째 작업'))
        source['projects'].append({'project': 'other', 'physical_worktrees': 1, 'errors': [],
                                   'tasks': [task(goal='셋째 작업')]})
        source['projects'][0]['tasks'].append(task(id=None, goal='거점', path='/repo'))
        text = render_board(source, width=120)
        self.assertIn('  ├─ app (2)', text)
        self.assertIn('  │  ├─ 첫 작업', text)
        self.assertIn('  │  │  다음: 실패 재현', text)
        self.assertIn('  │  └─ 둘째 작업', text)
        self.assertIn('  └─ other (1)', text)
        self.assertIn('     └─ 셋째 작업', text)
        self.assertIn('프로젝트 | 연결 작업자 | 창', text)
        for goal in ('첫 작업', '둘째 작업', '셋째 작업'):
            self.assertEqual(text.count(goal), 1)

    def test_completed_and_scheduled_planning_precedence_with_warnings(self):
        plan = {'scheduled_for': '2026-01-01', 'timezone': 'Asia/Seoul', 'later': True}
        complete = task(goal='끝난 작업', recorded_state='완료', state='확인필요',
                        identity_state='unknown', planning=plan, git_status=None)
        scheduled = task(goal='예정 작업', planning=plan, git_status=None)
        idea = task(goal='새 주제', path=None, planning={'later': True}, related_to='old', related_goal='기존 주제')
        self.assertEqual(section(complete), '완료')
        self.assertEqual(section(scheduled), '예정')
        self.assertEqual(section(idea), '나중에')
        text = render_board(report(complete, scheduled, idea), width=120)
        self.assertIn('완료 (1)', text)
        self.assertIn('예정 (1)', text)
        self.assertIn('Git 상태 조회 미확인', text)
        self.assertIn('아이디어 카드 · 폴더 없음', text)
        self.assertIn('관련 목표: 기존 주제', text)
        for goal in ('끝난 작업', '예정 작업', '새 주제'):
            self.assertEqual(text.count(goal), 1)

    def test_eight_old_paths_do_not_consume_generic_error_slots(self):
        source = report()
        source['projects'] = []
        for name, count in [('agents', 3), ('post-series', 3), ('awo', 2)]:
            rows = [task(path=f'/{name}/old-{i}', identity_state='unknown', git_status=None)
                    for i in range(count)]
            rows.append(task(path=f'/{name}/current', git_status=''))
            source['projects'].append({'project': name, 'tasks': rows, 'errors': []})
        source['multiple_agents'] = {'/agents/current': 4, '/post-series/current': 2, '/awo/current': 2}
        source['observed_agent_sessions'] = 8
        advice = board_advice(source)
        self.assertEqual(len(advice), 3)
        self.assertIn('복수 작업자 연결', advice[0]['evidence'])
        self.assertIn('작업폴더 연결 검증 실패 8개', advice[1]['evidence'])
        self.assertIn('집중할 작업 1개', advice[2]['action'])
        self.assertNotIn('Git 상태 조회 실패', str(advice))

    def test_generic_errors_and_dispatch_share_one_priority_slot(self):
        source = report(task(git_status=None))
        source['projects'][0]['errors'] = ['조회 실패']
        source['projects'].append({'project': 'other', 'tasks': [], 'errors': [],
                                   'dispatch_pending': {'state': 'pending'}})
        advice = board_advice(source)
        self.assertEqual(len(advice), 2)
        self.assertIn('app', advice[0]['evidence'])
        self.assertIn('Git 상태 조회 실패', advice[0]['evidence'])
        self.assertIn('other', advice[0]['evidence'])
        self.assertIn('이전 실행 결과 미확인', advice[0]['evidence'])
        source.update(session_state='unknown', observed_agent_sessions=None)
        advice = board_advice(source)
        self.assertEqual(len(advice), 1)
        self.assertIn('판단할 수 없습니다', advice[0]['evidence'])

    def test_advice_priorities_actual_duplicate_evidence_and_cap(self):
        terms = [{'handle': f't{i}', 'connected': True, 'agentIdentity': 'codex'} for i in range(4)]
        source = report(task(sessions={'state': 'present', 'terminals': terms}),
                        task(path='/repo/broken', identity_state='unknown'),
                        task(id=None, goal='미등록 작업', path='/repo/new'))
        source['projects'][0]['dispatch_pending'] = {'state': 'pending'}
        before = copy.deepcopy(source)
        advice = board_advice(source)
        self.assertEqual(len(advice), 3)
        self.assertIn('실행 결과 미확인', advice[0]['evidence'])
        self.assertEqual(advice[1]['scope'], '조회 범위')
        self.assertIn('app 4개', advice[1]['evidence'])
        self.assertIn('작업폴더 연결 검증 실패', advice[2]['evidence'])
        self.assertEqual(source, before)
        self.assertEqual(board_advice(source), advice)

    def test_duplicate_and_connection_failures_each_use_one_slot(self):
        source = report()
        source['projects'] = []
        source['observed_agent_sessions'] = 8
        for name, workers, failures in [('agents', 4, 3), ('21gram-partners', 2, 3), ('naver-rank-tracker', 2, 2)]:
            path = '/' + name
            rows = [task(path=path)] + [task(path=path + '/' + str(i), identity_state='unknown') for i in range(failures)]
            source['projects'].append({'project': name, 'tasks': rows, 'errors': []})
            source['multiple_agents'][path] = workers
        advice = board_advice(source)
        self.assertEqual(len(advice), 3)
        self.assertIn('agents 4개 · 21gram-partners 2개 · naver-rank-tracker 2개', advice[0]['evidence'])
        self.assertIn('작업폴더 연결 검증 실패 8개', advice[1]['evidence'])
        self.assertIn('집중할 작업 1개', advice[2]['action'])
        self.assertEqual([a['scope'] for a in advice], ['조회 범위', '조회 범위', '전체 환경'])
        source['multiple_agents']['/outside/unknown-project'] = 6
        advice = board_advice(source)
        self.assertEqual(advice[0]['scope'], '전체 환경 · 조회 범위 안팎')
        self.assertIn('프로젝트 미확인 6개 · agents 4개', advice[0]['evidence'])
        self.assertIn('외 1곳', advice[0]['evidence'])
        self.assertNotIn('unknown-project', str(advice))

    def test_advice_unknown_sessions_never_infer_counts_or_focus(self):
        source = report(task())
        source.update(session_state='unknown', observed_agent_sessions=None,
                      multiple_agents={'/somewhere': 9})
        advice = board_advice(source)
        self.assertEqual(len(advice), 1)
        self.assertEqual(advice[0]['scope'], '전체 환경')
        self.assertIn('판단할 수 없습니다', advice[0]['evidence'])
        self.assertNotIn('집중할', str(advice))
        self.assertNotIn('작업자 9개', str(advice))

    def test_advice_filtered_external_paths_do_not_invent_project_names(self):
        source = report(task(id=None, goal='미등록 작업'))
        source.update(observed_agent_sessions=3, multiple_agents={'/secret/fake-project/work': 2})
        advice = board_advice(source)
        self.assertEqual(advice[0]['scope'], '전체 환경 · 조회 범위 밖 (프로젝트 미확인)')
        self.assertIn('프로젝트 미확인 2개', advice[0]['evidence'])
        self.assertEqual(advice[1]['scope'], 'app')
        self.assertNotIn('fake-project', str(advice))
        self.assertNotIn('/secret', render_board(source))

    def test_advice_normal_empty_and_missing_user_next(self):
        source = report()
        source['observed_agent_sessions'] = 0
        self.assertEqual(board_advice(source), [])
        self.assertNotIn('지금 할 만한 일', render_board(source))
        opened = task(next='기록과 실제 상태를 확인하세요.', sessions={'state': 'present', 'terminals': [
            {'handle': 't1', 'connected': True, 'agentIdentity': 'codex'}]})
        source = report(opened)
        source['observed_agent_sessions'] = 1
        self.assertIn('사용자가 기록한 다음 행동이 없습니다', board_advice(source)[0]['evidence'])
        source['observed_agent_sessions'] = 5
        self.assertEqual(board_advice(source)[0]['scope'], '전체 환경')
        self.assertIn('직접 고르세요', board_advice(source)[0]['action'])

    def test_absent_window_and_legacy_state_are_not_broken_connections(self):
        self.assertEqual(section(task()), '이어갈 작업')
        self.assertEqual(section(task(identity_state='unknown')), '확인할 연결')
        missing = task()
        del missing['sessions']
        self.assertEqual(section(missing), '확인할 연결')
        unknown = task(sessions={'state': 'present', 'terminals': [{'handle': 'shell'}]})
        self.assertEqual(section(unknown), '확인할 연결')
        text = render_board(report(task()))
        self.assertNotIn('확인할 연결 (', text)
        self.assertIn('상태 미기록/확인필요 기록', text)

    def test_primary_and_unregistered_paths_do_not_invent_goals(self):
        primary = task(id=None, goal='거점', path='/repo')
        other = task(id=None, goal='미등록 작업', path='/repo/work/topic-x')
        text = render_board(report(primary, other))
        self.assertEqual(section(primary), '지시 거점')
        self.assertIn('지시 거점 (1)', text)
        self.assertIn('미등록 작업 · topic-x', text)
        self.assertNotIn('아이디어 (', text)
        self.assertNotIn('/repo', text)

    def test_scoped_totals_do_not_claim_global_agents_belong_to_project(self):
        opened = task(sessions={'state': 'present', 'terminals': [
            {'handle': 't1', 'agentIdentity': 'codex', 'connected': True}]})
        text = render_board(report(opened), width=120)
        self.assertIn('조회 범위 · 프로젝트 1개 · 실제 폴더 2개 · 연결된 agent 1개', text)
        self.assertIn('전체 환경 · 연결된 agent 7개', text)
        self.assertIn('열린 작업 (1)', text)
        self.assertIn('창 연결은 실행 중이라는 뜻이 아닙니다', text)

    def test_narrow_wrapping_details_and_input_immutability(self):
        source = report(task(goal='아주 긴 한국어 작업 목표를 확인하고 알림 누락 문제를 수정합니다',
                             next='다음 행동도 매우 길지만 화면 폭에 맞춰 모두 표시합니다'))
        before = copy.deepcopy(source)
        compact = render_board(source, width=36)
        self.assertTrue(all(cell_width(line) <= 36 for line in compact.splitlines()))
        self.assertNotIn('task-long-stable-identifier', compact)
        self.assertNotIn('awo cleanup', compact)
        detail = render_board(source, details=True, width=120)
        self.assertIn('task-long-stable-identifier', detail)
        self.assertIn('/repo/work/alerts', detail)
        self.assertIn('awo cleanup', detail)
        self.assertEqual(source, before)

    def test_json_with_details_remains_original_contract(self):
        source = report(task())
        stream = io.StringIO()
        with patch.object(awo_lifecycle, 'board', return_value=source), patch.object(
                sys, 'argv', ['awo_lifecycle', 'board', '--project', 'app', '--details', '--json']), patch('sys.stdout', stream):
            self.assertEqual(awo_lifecycle.main(), 0)
        self.assertEqual(json.loads(stream.getvalue()), source)

    def test_compact_repetition_preserves_every_task_and_user_next(self):
        source = report(task(goal='첫 작업', next='기록과 실제 상태를 확인하세요.'),
                        task(goal='둘째 작업', next='기록과 실제 상태를 확인하세요.'),
                        task(goal='셋째 작업', next='사용자가 남긴 다음 행동'),
                        task(id=None, goal='거점', path='/repo/main'))
        text = render_board(source, width=120)
        self.assertNotIn('기록과 실제 상태를 확인하세요.', text)
        self.assertNotIn('연결된 창 없음', text)
        self.assertEqual(text.count('상태 미기록/확인필요 기록'), 1)
        for goal in ('첫 작업', '둘째 작업', '셋째 작업', '사용자가 남긴 다음 행동'):
            self.assertIn(goal, text)
        self.assertIn('app | 0 | 0', text)
        self.assertNotIn('거점 · main', text)
        detail = render_board(source, details=True, width=120)
        self.assertEqual(detail.count('기록과 실제 상태를 확인하세요.'), 2)
