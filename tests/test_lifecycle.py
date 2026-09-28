"""End-to-end CLI lifecycle using temporary Git repositories and Orca doubles."""
import json
import os
from pathlib import Path
import socket
import subprocess
import unittest
from test_request import RequestTests, ROOT


class LifecycleTests(RequestTests):
    def setUp(self):
        super().setUp()
        fake = self.root / 'bin/orca'
        text = fake.read_text()
        text = text.replace("elif a[:2] == ['worktree', 'create']:", '''elif a[:2] == ['terminal', 'list']:
    if os.environ.get('TEST_AUTO_SESSIONS') and pathlib.Path(os.environ['TEST_SESSION']).exists():
        os.environ['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': pathlib.Path(os.environ['TEST_SESSION']).read_text(), 'connected': True, 'agentIdentity': 'codex'}]})
    print('{"terminals": []}' if pathlib.Path(os.environ['TEST_SESSION'] + '.closed').exists() else os.environ.get('TEST_TERMINALS', '{"terminals": []}'))
elif a[:2] == ['terminal', 'wait']:
    print(json.dumps({'result': {'wait': {'satisfied': os.environ.get('TEST_BUSY') != '1'}}}))
elif a[:2] == ['terminal', 'read']:
    screen = {'handle': 't1', 'source': 'screen', 'tail': ['ready'], 'draft': os.environ.get('TEST_DRAFT', ''), 'truncated': False, 'limited': os.environ.get('TEST_PARTIAL') == '1'}
    if os.environ.get('TEST_MISSING_DRAFT'): screen.pop('draft')
    print(json.dumps({'result': {'terminal': screen}}))
elif a[:2] == ['terminal', 'close']:
    tasks = json.loads(pathlib.Path(repo, '.git/awo/tasks.json').read_text())
    saved = next(t for t in tasks if t.get('close', {}).get('state') == 'attempting')
    assert pathlib.Path(saved['handoff']).is_file() and saved['next'] and saved['validation']
    pathlib.Path(os.environ['TEST_SESSION'] + '.closed').write_text('closed')
    print('{"ok": true}')
elif a[:2] == ['terminal', 'switch']:
    print('{"ok": true}')
elif a[:2] == ['terminal', 'create']:
    path = a[a.index('--worktree') + 1][5:]
    pathlib.Path(os.environ['TEST_SESSION']).write_text(path)
    print('{"terminal": {"handle": "t1"}}')
elif a[:2] == ['terminal', 'show']:
    path = pathlib.Path(os.environ['TEST_SESSION']).read_text()
    branch = subprocess.check_output(['git', '-C', path, 'symbolic-ref', 'HEAD'], text=True).strip()
    print(json.dumps({'terminal': {'handle': 't1', 'worktreePath': path, 'branch': branch, 'connected': True, 'agentIdentity': 'codex'}}))
elif a[:2] == ['worktree', 'create']:''')
        text = text.replace("    print(json.dumps({'ok': True, 'result': {'path': path}}))", "    pathlib.Path(os.environ['TEST_SESSION']).write_text(path)\n    print(json.dumps({'ok': True, 'result': {'path': path, 'startupTerminal': {'handle': 't1'}}}))")
        fake.write_text(text)
        self.env['TEST_SESSION'] = str(self.root / 'session')

    def cli(self, *args, success=True):
        return self.run_cmd(str(ROOT / 'bin/awo'), *args, success=success)

    def obj(self, *args, **kw):
        return json.loads(self.cli(*args, **kw).stdout)

    def imported(self):
        path = self.root / 'existing'
        self.git('worktree', 'add', '-b', 'existing', str(path))
        task = self.obj('task', 'import', 'secretary', '알림 수정', '--worktree', str(path))
        return task, path

    def test_add_has_stable_id_without_worktree_and_bind_explicit(self):
        task = self.obj('task', 'add', 'secretary', '한국어 목표', '--next', '재현하기')
        self.assertTrue(task['id'].startswith('task-'))
        self.assertIsNone(task['path'])
        self.assertFalse(self.calls.exists())
        same = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(same['id'], task['id'])
        path = self.root / 'existing'
        self.git('worktree', 'add', '-b', 'existing', str(path))
        bound = self.obj('task', 'bind', 'secretary', task['id'], '--worktree', str(path))
        self.assertEqual(bound['id'], task['id'])
        self.assertEqual(bound['path'], str(path))

    def test_park_preserves_dirty_ignored_new_process_resume(self):
        task, path = self.imported()
        (path / 'code.txt').write_text('dirty user content')
        (path / '.gitignore').write_text('artifact.log\n')
        (path / 'artifact.log').write_bytes(b'private artifact')
        before = {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}
        parked = self.obj('task', 'park', 'secretary', task['id'], '--processes-checked', '--next', '실패 테스트부터', '--validation', '재현 완료')
        self.assertEqual(parked['state'], '보관')
        note = Path(parked['handoff'])
        contents = note.read_bytes()
        resumed = self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        self.assertEqual(resumed['dispatch']['state'], 'session_confirmed')
        self.assertEqual(resumed['path'], str(path))
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()})
        self.assertEqual(note.read_bytes(), contents)
        parked2 = self.obj('task', 'park', 'secretary', task['id'], '--processes-checked')
        self.assertNotEqual(parked2['handoff'], str(note))
        self.assertTrue(note.exists())
        board = self.obj('board', '--cleanup', '--json')
        item = next(t for t in board['projects'][0]['tasks'] if t.get('id') == task['id'])
        self.assertEqual(item['cleanup']['classification'], 'BLOCKED')

    def test_park_new_process_connects_exact_existing_session(self):
        task, path = self.imported()
        self.obj('task', 'park', 'secretary', task['id'], '--processes-checked', '--next', '회귀 시험', '--validation', '기본 통과')
        self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        create = next(c for c in calls if c[:2] == ['terminal', 'create'])
        prompt = create[create.index('--command') + 1]
        self.assertIn('회귀 시험', prompt)
        self.assertIn('기본 통과', prompt)
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        result = self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        self.assertEqual(result['dispatch']['state'], 'existing_session_connected')
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(sum(c[:2] == ['terminal', 'create'] for c in calls), 1)
        self.assertIn(['terminal', 'switch', '--terminal', 't1', '--json'], calls)

    def test_multiple_and_unknown_workers_never_switch_or_create(self):
        task, path = self.imported()
        known = {'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}
        for rows in ([known, known], [{'handle': 'shell', 'worktreePath': str(path)}]):
            self.env['TEST_TERMINALS'] = json.dumps({'terminals': rows})
            self.assertNotEqual(self.cli('task', 'resume', 'secretary', task['id'], '--agent', 'codex', success=False).returncode, 0)
        self.assertNotIn('switch', self.calls.read_text())
        self.assertNotIn('create', self.calls.read_text())

    def test_light_board_korean_labels_and_actual_wip(self):
        task, path = self.imported()
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [
            {'handle': str(i), 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True} for i in range(4)]})
        report = self.obj('board', '--json')
        self.assertEqual(report['observed_agent_sessions'], 4)
        self.assertEqual(report['multiple_agents'][str(path)], 4)
        self.assertTrue(report['warnings'])
        text = self.cli('board').stdout
        self.assertNotIn('present', text)
        self.assertNotIn('UNKNOWN', text)
        self.assertIn('미검사', text)

    def test_related_topic_start_independent_base_preserves_old_dirty(self):
        self.config.write_text(self.config.read_text().replace('max_worktrees: 2', 'max_worktrees: 3'))
        old, path = self.imported()
        (path / 'code.txt').write_text('old unfinished work')
        new = self.obj('task', 'add', 'secretary', '을지로 변화', '--related-to', old['id'], '--next', '자료 조사')
        self.assertNotEqual(new['id'], old['id'])
        self.assertIsNone(new['path'])
        self.assertFalse(self.calls.exists())
        started = self.obj('task', 'start', 'secretary', new['id'], '--agent', 'codex')
        self.assertEqual(started['state'], '진행')
        self.assertNotEqual(started['path'], str(path))
        self.assertEqual(started['related_to'], old['id'])
        self.assertEqual(Path(started['path'], 'code.txt').read_text(), 'initial\n')
        self.assertEqual((path / 'code.txt').read_text(), 'old unfinished work')
        self.assertEqual(self.run_cmd('git', '-C', started['path'], 'rev-parse', 'HEAD').stdout.strip(), self.git('rev-parse', 'origin/main'))
        self.assertNotEqual(started['branch'], old['branch'])
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        created = next(c for c in calls if c[:2] == ['worktree', 'create'])
        self.assertIn('--no-parent', created)
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        (self.root / 'session').write_text(str(path))
        returned = self.obj('task', 'resume', 'secretary', old['id'], '--agent', 'codex')
        self.assertEqual(returned['dispatch']['terminal_id'], 't1')
        self.assertEqual(self.obj('task', 'show', 'secretary', new['id'])['next'], '자료 조사')
        self.assertEqual(self.obj('task', 'show', 'secretary', old['id'])['goal'], old['goal'])

    def test_task_start_at_limit_keeps_todo_and_no_pending(self):
        old, path = self.imported()
        new = self.obj('task', 'add', 'secretary', '다른 주제', '--related-to', old['id'])
        self.assertNotEqual(self.cli('task', 'start', 'secretary', new['id'], '--agent', 'codex', success=False).returncode, 0)
        self.assertFalse((self.repo / '.git/awo/dispatch.json').exists())
        self.assertIsNone(self.obj('task', 'show', 'secretary', new['id'])['path'])

    def test_park_close_idle_only_after_handoff_then_exact_close(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        self.env.pop('ORCA_TERMINAL_HANDLE', None)
        result = self.obj('task', 'park', 'secretary', task['id'], '--close', '--processes-checked', '--next', '계속 수정', '--validation', '부분 통과')
        self.assertEqual(result['state'], '보관')
        self.assertEqual(result['close']['state'], 'closed')
        self.assertTrue(Path(result['handoff']).exists())
        self.assertTrue(path.exists())
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(sum(c[:2] == ['terminal', 'wait'] for c in calls), 2)
        self.assertIn(['terminal', 'close', '--terminal', 't1', '--json'], calls)

    def test_park_close_busy_draft_and_self_never_close(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        for key, value in [('TEST_BUSY', '1'), ('TEST_DRAFT', 'unsent'), ('TEST_PARTIAL', '1'), ('TEST_MISSING_DRAFT', '1'), ('ORCA_TERMINAL_HANDLE', 't1')]:
            self.env[key] = value
            self.assertNotEqual(self.cli('task', 'park', 'secretary', task['id'], '--close', '--processes-checked', '--next', '계속', '--validation', '미검증', success=False).returncode, 0)
            del self.env[key]
        self.assertFalse((self.root / 'session.closed').exists())
        self.assertNotIn('"close"', self.calls.read_text())

    def test_two_process_resume_never_creates_two_workers(self):
        task, path = self.imported()
        self.env['TEST_AUTO_SESSIONS'] = '1'
        argv = [str(ROOT / 'bin/awo'), 'task', 'resume', 'secretary', task['id'], '--agent', 'codex']
        processes = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env) for _ in range(2)]
        results = [p.communicate(timeout=30) for p in processes]
        self.assertIn(0, [p.returncode for p in processes], results)
        self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        self.assertEqual(sum(c[:2] == ['terminal', 'create'] for c in calls), 1)

    def test_board_existing_metadata_bytes_and_mtime_unchanged(self):
        task, path = self.imported()
        folder = self.repo / '.git/awo'
        def snapshot():
            return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob('*') if p.is_file()}
        before = snapshot()
        self.obj('board', '--json')
        self.obj('board', '--cleanup', '--json')
        self.assertEqual(before, snapshot())

    def test_missing_draft_only_explicit_input_confirmation_allows_close(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env.pop('ORCA_TERMINAL_HANDLE', None)
        self.env['TEST_MISSING_DRAFT'] = '1'
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        result = self.obj('task', 'park', 'secretary', task['id'], '--close', '--processes-checked', '--input-checked', '--next', '이어하기', '--validation', '미검증')
        self.assertEqual(result['close']['state'], 'closed')

    def test_unknown_or_present_session_never_claims_parked(self):
        task, path = self.imported()
        for value in ('{"terminals": [], "truncated": true}', json.dumps({'terminals': [{'handle': 't', 'worktreePath': str(path)}]}), 'bad json'):
            self.env['TEST_TERMINALS'] = value
            result = self.obj('task', 'park', 'secretary', task['id'], '--processes-checked')
            self.assertEqual(result['state'], '확인필요')
            self.assertTrue(Path(result['handoff']).exists())
        self.env['TEST_TERMINALS'] = '{"terminals": []}'
        self.assertEqual(self.obj('task', 'park', 'secretary', task['id'])['state'], '확인필요')

    def test_branch_and_path_replacement_refused(self):
        task, path = self.imported()
        self.run_cmd('git', '-C', str(path), 'checkout', '-b', 'replacement')
        self.assertNotEqual(self.cli('task', 'resume', 'secretary', task['id'], success=False).returncode, 0)
        self.git('worktree', 'remove', str(path))
        self.git('worktree', 'add', '-b', 'again', str(path))
        self.assertNotEqual(self.cli('task', 'resume', 'secretary', task['id'], success=False).returncode, 0)

    def test_board_no_metadata_writes_one_inventory_errors_isolated(self):
        path = self.root / 'unregistered'
        self.git('worktree', 'add', '-b', 'unregistered', str(path))
        with self.config.open('a') as f:
            f.write(f'  offline:\n    path: "{self.root / "missing"}"\n')
        report = self.obj('board', '--json')
        self.assertFalse((self.repo / '.git/awo').exists())
        self.assertTrue(report['projects'][1]['errors'])
        self.assertTrue(any(t['goal'] == '미등록 작업' for t in report['projects'][0]['tasks']))
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)
        folder = self.repo / '.git/awo'
        folder.mkdir()
        (folder / 'tasks.json').write_text('{corrupt')
        self.env['TEST_TERMINALS'] = '{"terminals": [], "truncated": true}'
        report = self.obj('board', '--json')
        self.assertEqual(report['session_state'], 'unknown')
        self.assertTrue(report['projects'][0]['errors'])
        self.assertEqual((folder / 'tasks.json').read_text(), '{corrupt')

    def test_existing_terminal_returned_without_creation(self):
        task, path = self.imported()
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        (self.root / 'session').write_text(str(path))
        result = self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        self.assertEqual(result['dispatch']['state'], 'existing_session_connected')
        self.assertEqual(result['dispatch']['terminal_id'], 't1')
        self.assertNotIn('create', self.calls.read_text())

    def test_incomplete_resume_blocks_and_requires_reconciliation(self):
        task, path = self.imported()
        self.env['TEST_TERMINALS'] = '{"terminals": [], "truncated": true}'
        self.assertNotEqual(self.cli('task', 'resume', 'secretary', task['id'], '--agent', 'codex', success=False).returncode, 0)
        self.env['TEST_TERMINALS'] = '{"terminals": []}'
        # Failed read-only preflight made no dispatch attempt, so no pending intent.
        self.assertFalse((self.repo / '.git/awo/dispatch.json').exists())
        result = self.obj('task', 'resume', 'secretary', task['id'], '--agent', 'codex')
        self.assertEqual(result['dispatch']['state'], 'session_confirmed')

    def test_resources_conflict_overlap_occupied_and_release(self):
        a = self.obj('task', 'add', 'secretary', 'A')['id']
        b = self.obj('task', 'add', 'secretary', 'B')['id']
        for kind, value in [('db', 'local/db/tenant'), ('output', str(self.root / 'out'))]:
            self.obj('resource', 'register', 'secretary', a, kind, value)
            result = self.cli('resource', 'register', 'secretary', b, kind, value, success=False)
            self.assertNotEqual(result.returncode, 0)
        result = self.cli('resource', 'register', 'secretary', b, 'output', str(self.root / 'out/sub'), success=False)
        self.assertNotEqual(result.returncode, 0)
        self.obj('resource', 'release', 'secretary', a, 'db', 'local/db/tenant')
        self.obj('resource', 'register', 'secretary', b, 'db', 'local/db/tenant')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            value = str(sock.getsockname()[1])
            self.assertFalse(self.obj('resource', 'check', 'port', value)['available_now'])
            self.assertNotEqual(self.cli('resource', 'register', 'secretary', a, 'port', value, success=False).returncode, 0)
        self.assertFalse((self.root / 'out').exists())

    def test_request_preserves_stable_id_and_history(self):
        task, path = self.imported()
        self.report('--goal', task['goal'], '--apply')
        after = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(after['events'][0]['action'], 'add')
        self.assertEqual(after['events'][-1]['action'], 'request')

    def test_shared_project_lock_blocks_resume_request_and_start(self):
        import fcntl
        task, path = self.imported()
        with (self.repo / '.git/awo-dispatch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for args in [('task', 'resume', 'secretary', task['id']),
                         ('start', 'secretary', 'existing', 'codex', '알림 수정', '--worktree', str(path)),
                         ('request', 'AWO 카카오 비서', '--goal', '알림 수정', '--apply')]:
                self.assertNotEqual(self.cli(*args, success=False).returncode, 0)
        self.assertFalse(self.calls.exists())
