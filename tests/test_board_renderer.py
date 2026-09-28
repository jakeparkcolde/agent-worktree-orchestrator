"""Pure presentation tests: no Git, Orca, config or filesystem mutation."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from awo_board import cell_width, render_board, section
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
        self.assertIn('  - app · 연결 agent 0 / 창 0', text)
        self.assertNotIn('거점 · main', text)
        detail = render_board(source, details=True, width=120)
        self.assertEqual(detail.count('기록과 실제 상태를 확인하세요.'), 2)
