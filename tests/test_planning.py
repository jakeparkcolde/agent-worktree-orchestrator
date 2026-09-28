"""Planning and recommendations on synthetic temporary Git; no production I/O."""
import copy
import json
from pathlib import Path
import sys
import unittest
import test_lifecycle as fixtures
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from awo_board import render_board, section
from awo_planning import recommend


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.LifecycleTests(methodName='test_add_has_stable_id_without_worktree_and_bind_explicit')
        self.addCleanup(self.fx.doCleanups)
        self.fx.setUp()

    def test_plan_preserves_identity_safety_and_unknown_metadata(self):
        f = self.fx
        task, path = f.imported()
        file = f.repo / '.git/awo/tasks.json'
        rows = json.loads(file.read_text())
        rows[0].update(state='확인필요', future_field={'keep': 17}, planning={'custom': 'keep'})
        file.write_text(json.dumps(rows))
        before = json.loads(file.read_text())[0]
        planned = f.obj('task', 'plan', 'secretary', task['id'], '--later', '--date', '2026-10-03', '--next', '자료 조사')
        for key in ('id', 'goal', 'path', 'branch', 'identity', 'state', 'future_field'):
            self.assertEqual(planned[key], before[key])
        self.assertEqual(planned['planning'], {'custom': 'keep', 'later': True, 'scheduled_for': '2026-10-03', 'timezone': 'Asia/Seoul'})
        self.assertEqual(planned['events'][:-1], before['events'])
        updated = f.obj('task', 'update', 'secretary', task['id'], '--clear-date', '--clear-later', '--clear-next')
        self.assertEqual(updated['planning'], {'custom': 'keep'})
        self.assertEqual(updated['next'], '')
        self.assertEqual(updated['identity'], task['identity'])
        self.assertFalse(f.calls.exists())

    def test_add_import_options_and_invalid_dates_do_not_change_record(self):
        f = self.fx
        task = f.obj('task', 'add', 'secretary', '나중 아이디어', '--later', '--date', '2028-02-29', '--next', '준비')
        self.assertIsNone(task['path'])
        self.assertEqual(task['planning']['scheduled_for'], '2028-02-29')
        file = f.repo / '.git/awo/tasks.json'
        before = file.read_bytes()
        for value in ('2026-02-29', '2026-2-01', '2026-13-01', '2026-10-01T00:00', '20261001'):
            result = f.cli('task', 'plan', 'secretary', task['id'], '--date', value, success=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(file.read_bytes(), before)
        path = f.root / 'planned'
        f.git('worktree', 'add', '-b', 'planned', str(path))
        imported = f.obj('task', 'import', 'secretary', '기존 계획', '--worktree', str(path), '--date', '2026-10-04', '--later')
        self.assertEqual(imported['planning']['timezone'], 'Asia/Seoul')
        self.assertEqual(imported['path'], str(path))
        self.assertFalse(f.calls.exists())

    def test_park_display_and_scheduled_unknown_stays_in_one_section(self):
        f = self.fx
        task, path = f.imported()
        parked = f.obj('task', 'park', 'secretary', task['id'], '--processes-checked', '--next', '이어하기')
        self.assertEqual(parked['state'], '보관')
        self.assertEqual(section(parked), '나중에')
        f.obj('task', 'plan', 'secretary', task['id'], '--date', '2026-10-03')
        f.git('worktree', 'remove', str(path))
        report = f.obj('board', '--json')
        row = next(r for r in report['projects'][0]['tasks'] if r.get('id') == task['id'])
        self.assertEqual(row['identity_state'], 'unknown')
        self.assertEqual(section(row), '예정')
        text = render_board(report, width=120)
        self.assertIn('예정 (1)', text)
        self.assertEqual(text.count('알림 수정'), 1)
        self.assertIn('폴더 연결 검증 실패', text)
        self.assertIn('2026-10-03 (KST)', text)
        self.assertNotIn('확인할 연결 (', text)

    def test_suggest_preview_no_metadata_or_orca_then_apply_idea_only(self):
        f = self.fx
        result = f.obj('task', 'suggest', 'secretary', '--goal', '을지로 변화', '--intent', 'later', '--next', '자료 조사')
        self.assertEqual(result['recommendation'], 'later')
        self.assertFalse((f.repo / '.git/awo').exists())
        self.assertFalse(f.calls.exists())
        result = f.obj('task', 'suggest', 'secretary', '--goal', '을지로 변화', '--intent', 'later', '--date', '2026-10-03', '--next', '자료 조사', '--apply')
        self.assertEqual(result['mode'], 'APPLY')
        self.assertIsNone(result['task']['path'])
        self.assertEqual(result['task']['planning']['later'], True)
        self.assertFalse(f.calls.exists())
        self.assertEqual(len(f.git('worktree', 'list', '--porcelain').split('worktree ')) - 1, 1)

    def test_completed_old_scheduled_path_stays_completed_with_warning(self):
        f = self.fx
        task, path = f.imported()
        f.obj('task', 'plan', 'secretary', task['id'], '--date', '2026-01-01', '--later')
        f.obj('task', 'done', 'secretary', task['id'], '--processes-checked', '--validation', '검증 완료')
        f.git('worktree', 'remove', str(path))
        report = f.obj('board', '--json')
        row = next(r for r in report['projects'][0]['tasks'] if r.get('id') == task['id'])
        self.assertEqual(row['recorded_state'], '완료')
        self.assertEqual(row['state'], '확인필요')
        self.assertEqual(section(row), '완료')
        text = render_board(report, width=120)
        self.assertIn('완료 (1)', text)
        self.assertNotIn('예정 (', text)
        self.assertIn('폴더 연결 검증 실패', text)

    def test_separate_explicit_even_same_goal_then_start_only_existing_flow(self):
        f = self.fx
        old = f.obj('task', 'add', 'secretary', '성수동 변화')
        request = ['task', 'suggest', 'secretary', '--goal', '성수동 변화', '--current-task', old['id'], '--intent', 'separate']
        file = f.repo / '.git/awo/tasks.json'
        before = file.read_bytes()
        self.assertEqual(f.obj(*request)['recommendation'], 'separate')
        self.assertEqual(before, file.read_bytes())
        new = f.obj(*request, '--apply')['task']
        self.assertNotEqual(new['id'], old['id'])
        self.assertEqual(new['related_to'], old['id'])
        self.assertIsNone(new['path'])
        self.assertFalse(f.calls.exists())
        started = f.obj('task', 'start', 'secretary', new['id'], '--agent', 'codex')
        self.assertEqual(started['dispatch']['state'], 'session_confirmed')
        self.assertEqual(f.obj('task', 'show', 'secretary', old['id']), old)

    def test_needs_choice_apply_never_saves_and_reuse_only_selects(self):
        f = self.fx
        old = f.obj('task', 'add', 'secretary', '성수동 변화')
        file = f.repo / '.git/awo/tasks.json'
        before = file.read_bytes()
        ambiguous = f.obj('task', 'suggest', 'secretary', '--goal', '성수동 변화', '--current-task', old['id'])
        self.assertEqual(ambiguous['recommendation'], 'needs-choice')
        blocked = f.cli('task', 'suggest', 'secretary', '--goal', '성수동 변화', '--current-task', old['id'],
                        '--context', '나중에 해보자', '--apply', success=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertEqual(file.read_bytes(), before)
        reused = f.obj('task', 'suggest', 'secretary', '--goal', '성수동 보완', '--current-task', old['id'], '--intent', 'reuse', '--apply')
        self.assertEqual(reused['target_id'], old['id'])
        self.assertEqual(file.read_bytes(), before)
        self.assertFalse(f.calls.exists())
        failed = f.cli('task', 'suggest', 'secretary', '--goal', '새것', '--current-task', 'missing-id', '--intent', 'later', '--apply', success=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(file.read_bytes(), before)

    def test_context_recommendation_is_explicit_and_pure(self):
        tasks = [{'id': 'old', 'goal': '성수동 변화'}]
        before = copy.deepcopy(tasks)
        for context, expected in [('을지로도 나중에 해보자', 'later'),
                                  ('비슷하지만 새 주제로 따로 열어줘', 'separate'),
                                  ('이거 더 고치자', 'needs-choice'),
                                  ('새 주제로 따로 열어줄까?', 'needs-choice'),
                                  ('따로 열어 말고 나중에', 'needs-choice'),
                                  ('나중에 하지 말고', 'needs-choice')]:
            self.assertEqual(recommend(tasks, '을지로 변화', 'old', context=context)['recommendation'], expected)
        self.assertEqual(recommend(tasks, '성수동 변화', 'old')['recommendation'], 'needs-choice')
        self.assertEqual(recommend(tasks, '성수동 변화', 'old', context='이거 더 고치자')['recommendation'], 'reuse')
        self.assertEqual(recommend(tasks, '성수동 변화', intent='reuse')['recommendation'], 'needs-choice')
        self.assertEqual(recommend(tasks, '성수동 변화', 'old', 'separate', '이거 더 고치자')['recommendation'], 'separate')
        self.assertEqual(tasks, before)

    def test_idea_apply_retries_deduplicate_and_new_request_is_explicit(self):
        f = self.fx
        old = f.obj('task', 'add', 'secretary', '성수동 변화')
        argv = ['task', 'suggest', 'secretary', '--goal', '을지로 변화', '--current-task', old['id'],
                '--intent', 'separate', '--apply']
        first = f.obj(*argv)['task']
        file = f.repo / '.git/awo/tasks.json'
        before = file.read_bytes()
        retry = f.obj(*argv)
        self.assertTrue(retry['deduplicated'])
        self.assertEqual(retry['task']['id'], first['id'])
        self.assertEqual(file.read_bytes(), before)
        conflict = f.cli(*argv, '--next', '내용 변경', success=False)
        self.assertNotEqual(conflict.returncode, 0)
        self.assertEqual(file.read_bytes(), before)
        another = f.obj(*argv, '--request-id', 'topic-variant-2')['task']
        self.assertNotEqual(another['id'], first['id'])
        self.assertEqual(f.obj(*argv, '--request-id', 'topic-variant-2')['task']['id'], another['id'])
        self.assertFalse(f.calls.exists())

    def test_auto_apply_without_tasks_cannot_even_create_metadata(self):
        f = self.fx
        result = f.cli('task', 'suggest', 'secretary', '--goal', '을지로 변화',
                       '--context', '나중에 해보자', '--apply', success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((f.repo / '.git/awo').exists())
        self.assertFalse(f.calls.exists())
