"""Lifecycle regressions: only temporary Git repositories and Orca doubles."""
import json
from pathlib import Path
from test_lifecycle import LifecycleTests


class CompletionTests(LifecycleTests):
    def drift(self):
        task, path = self.imported()
        file = self.repo / '.git/awo/tasks.json'
        rows = json.loads(file.read_text())
        rows[0]['identity'][1] += 1
        file.write_text(json.dumps(rows))
        return rows[0], path, file

    def test_request_never_overwrites_device_drift(self):
        task, path, file = self.drift()
        before = file.read_bytes()
        report = self.report('--goal', task['goal'], '--worktree', str(path), '--apply', success=False)
        self.assertEqual(report['action'], 'blocked')
        self.assertIn('repair', report['reason'])
        self.assertEqual(before, file.read_bytes())

    def test_finish_preview_is_read_only(self):
        task, path = self.imported()
        file = self.repo / '.git/awo/tasks.json'
        before = file.read_bytes()
        result = self.obj('task', 'finish', 'secretary', task['id'])
        self.assertEqual(result['mode'], 'PREVIEW')
        self.assertEqual(before, file.read_bytes())

    def finish(self, task, *args, **kwargs):
        return self.obj('task', 'finish', 'secretary', task['id'], *args, **kwargs)

    def metadata(self):
        root = self.repo / '.git/awo'
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}

    def owner(self, path, names):
        directory = self.root / 'ledger'
        directory.mkdir(exist_ok=True)
        self.env['AWO_LEDGER_DIR'] = str(directory)
        (directory / '2026-10.jsonl').write_text(''.join(json.dumps({'ts': 1, 'repo': str(path), 'rel': n, 'session': 'owner'}) + '\n' for n in names))

    def commit_args(self, *names):
        return [*sum((['--file', n] for n in names), []), '--message', 'explicit finish',
                '--owner-session', 'owner', '--ownership-checked']

    def test_repair_preview_apply_token_history_and_stable_id(self):
        task, path, file = self.drift()
        before = self.metadata()
        report = self.obj('task', 'diagnose', 'secretary', task['id'])
        self.assertTrue(report['repairable'])
        self.assertEqual(before, self.metadata())
        self.cli('task', 'repair', 'secretary', task['id'], '--apply', success=False)
        self.assertEqual(before[file.as_posix()], self.metadata()[file.as_posix()])
        result = self.obj('task', 'repair', 'secretary', task['id'], '--apply', '--snapshot', report['snapshot'])
        self.assertTrue(result['repaired'])
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['id'], task['id'])
        self.assertEqual(saved['events'][-1]['previous']['identity'], task['identity'])
        self.obj('task', 'resume', 'secretary', task['id'])

    def test_repair_stale_branch_and_recreated_path_refused(self):
        task, path, file = self.drift()
        token = self.obj('task', 'diagnose', 'secretary', task['id'])['snapshot']
        self.run_cmd('git', '-C', str(path), 'checkout', '-b', 'replacement')
        result = self.cli('task', 'repair', 'secretary', task['id'], '--apply', '--snapshot', token, success=False)
        self.assertNotEqual(result.returncode, 0)
        self.git('worktree', 'remove', str(path))
        self.git('worktree', 'add', '-b', 'another', str(path))
        self.assertFalse(self.obj('task', 'diagnose', 'secretary', task['id'])['repairable'])

    def test_invalid_goal_cannot_bypass_via_new_goal_slug_or_path(self):
        task, path, file = self.drift()
        self.config.write_text(self.config.read_text().replace('max_worktrees: 2', 'max_worktrees: 5'))
        other = self.root / 'other'
        self.git('worktree', 'add', '-b', 'other', str(other))
        before = file.read_bytes()
        for extra in (['--new-goal'], ['--task', 'different'], ['--worktree', str(other)]):
            report = self.report('--goal', task['goal'], '--apply', *extra, success=False)
            self.assertEqual(report['action'], 'blocked')
        new = self.obj('task', 'add', 'secretary', task['goal'])
        result = self.cli('task', 'start', 'secretary', new['id'], '--agent', 'codex', success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('repair', result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(json.loads(before)[0], json.loads(file.read_text())[0])

    def test_finish_all_preview_metadata_and_mtime_unchanged(self):
        task, path = self.imported()
        self.cli('audit', 'secretary', '--json')
        before = self.metadata()
        result = self.finish(task, '--cleanup', '--close', '--validate', 'false')
        self.assertEqual(result['mode'], 'PREVIEW')
        self.assertEqual(before, self.metadata())
        self.assertNotIn('"close"', self.calls.read_text())

    def test_finish_validation_failure_and_mutation_block_all_actions(self):
        task, path = self.imported()
        for command in ('false', 'printf changed > code.txt'):
            result = self.finish(task, '--apply', '--validate', command, '--close', '--cleanup', '--processes-checked')
            self.assertIn('blocked', result)
            saved = self.obj('task', 'show', 'secretary', task['id'])
            self.assertIn(saved['finish']['validation']['state'], ('failed', 'stale'))
            run = saved['finish']['validation']['runs'][-1]
            self.assertEqual(run['cwd'], str(path))
            self.assertIn('exit_code', run)
            self.assertNotIn('"close"', self.calls.read_text())
            self.assertTrue(path.exists())

    def test_same_status_content_change_invalidates_evidence(self):
        task, path = self.imported()
        (path / 'code.txt').write_text('first dirty')
        self.finish(task, '--apply', '--validate', 'true')
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['finish']['validation']['state'], 'passed')
        (path / 'code.txt').write_text('other dirty')
        result = self.finish(task, '--apply', '--close', '--cleanup')
        self.assertIn('blocked', result)
        self.assertEqual(result['validation']['state'], 'required')
        self.assertNotIn('"close"', self.calls.read_text())

    def test_commit_explicit_literal_filename_and_idempotence(self):
        task, path = self.imported()
        name = ':(glob)*.txt'
        (path / name).write_text('literal data')
        self.owner(path, [name])
        args = self.commit_args(name)
        result = self.finish(task, '--apply', '--validate', 'true', *args)
        self.assertNotIn('blocked', result)
        head = self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout
        self.assertEqual(result['integration']['state'], 'merge_pending')
        self.assertEqual(result['label'], '완료·병합대기')
        again = self.finish(task, '--apply', '--validate', 'true', *args)
        self.assertNotIn('blocked', again)
        self.assertEqual(head, self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout)
        self.assertTrue(Path(self.obj('task', 'show', 'secretary', task['id'])['handoff']).exists())

    def test_outside_staged_and_ambiguous_ownership_preserved(self):
        task, path = self.imported()
        (path / 'code.txt').write_text('mine')
        (path / 'other').write_text('theirs')
        self.run_cmd('git', '-C', str(path), 'add', 'other')
        before = self.run_cmd('git', '-C', str(path), 'diff', '--cached').stdout
        self.owner(path, ['code.txt'])
        result = self.finish(task, '--apply', '--validate', 'true', *self.commit_args('code.txt'))
        self.assertIn('blocked', result)
        self.assertEqual(before, self.run_cmd('git', '-C', str(path), 'diff', '--cached').stdout)
        result = self.finish(task, '--apply', *self.commit_args('code.txt', 'other'))
        self.assertIn('blocked', result)
        self.assertEqual(before, self.run_cmd('git', '-C', str(path), 'diff', '--cached').stdout)

    def test_commit_hook_mutation_blocks_close_cleanup(self):
        task, path = self.imported()
        (path / 'code.txt').write_text('mine')
        self.owner(path, ['code.txt'])
        hook = self.repo / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nprintf hook-change > code.txt\n')
        hook.chmod(0o755)
        result = self.finish(task, '--apply', '--validate', 'true', *self.commit_args('code.txt'), '--close', '--cleanup')
        self.assertIn('blocked', result)
        self.assertNotIn('"close"', self.calls.read_text())
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['finish']['commit']['state'], 'attempting')
        head = self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout
        result = self.finish(task, '--apply', '--validate', 'true', *self.commit_args('code.txt'))
        self.assertIn('미확인', result['blocked'])
        self.assertEqual(head, self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout)

    def test_finish_recent_cleanup_and_busy_session_pending(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        self.env['TEST_BUSY'] = '1'
        result = self.finish(task, '--apply', '--validate', 'true', '--close', '--cleanup', '--processes-checked', '--next', 'merge review')
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['state'], '완료')
        self.assertEqual(saved['finish']['session']['state'], 'pending')
        self.assertEqual(result['cleanup']['inspection']['classification'], 'ACTIVE')
        self.assertTrue(path.exists())
        self.assertNotIn('"close"', self.calls.read_text())

    def test_finish_close_shared_preservation_and_board(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env.pop('ORCA_TERMINAL_HANDLE', None)
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        result = self.finish(task, '--apply', '--validate', 'true', '--close', '--processes-checked', '--next', 'review')
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['state'], '완료')
        self.assertEqual(saved['finish']['session']['state'], 'closed')
        self.assertTrue(path.exists())
        self.assertIn('완료·정리대기', self.cli('board', '--include-done', '--details').stdout)
        self.assertIn('숨김', self.cli('board').stdout)

    def test_board_finish_cleanup_only_when_requested_and_once_per_project(self):
        import os
        import sys
        from unittest.mock import patch
        from test_request import ROOT
        sys.path.insert(0, str(ROOT / 'scripts'))
        import awo_lifecycle as life
        task, path = self.imported()
        self.finish(task, '--apply', '--validate', 'true')
        before = self.metadata()
        with patch.dict(os.environ, self.env):
            with patch.object(life, 'cleanup_preview', side_effect=AssertionError('unexpected cleanup')):
                report = life.board('secretary')
            row = next(t for t in report['projects'][0]['tasks'] if t.get('id') == task['id'])
            self.assertEqual(row['lifecycle_label'], '완료·정리대기')
            self.assertTrue(any('미검사' in step for step in row['remaining_steps']))
            with patch.object(life, 'cleanup_preview', wraps=life.cleanup_preview) as inspect:
                life.board('secretary', include_cleanup=True)
                self.assertEqual(inspect.call_count, 1)
        self.assertEqual(before, self.metadata())

    def test_resumed_session_and_shell_edits_allow_explicit_current_ownership(self):
        task, path = self.imported()
        self.owner(path, ['code.txt'])  # historical owner differs from resumed session
        self.run_cmd('sh', '-c', 'printf shell-edit > "$1/code.txt"', 'sh', str(path))
        result = self.finish(task, '--apply', '--validate', 'true', '--file', 'code.txt',
                             '--message', 'resumed shell change', '--owner-session', 'new-session', '--ownership-checked')
        self.assertNotIn('blocked', result)
        (path / 'shell-only').write_text('no ledger row')
        result = self.finish(task, '--apply', '--validate', 'true', '--file', 'shell-only',
                             '--message', 'shell file', '--ownership-checked')
        self.assertNotIn('blocked', result)

    def test_validation_ignored_build_output_and_touch_preserve_source_evidence(self):
        task, path = self.imported()
        (path / '.gitignore').write_text('build/\n')
        self.run_cmd('git', '-C', str(path), 'add', '.gitignore')
        self.run_cmd('git', '-C', str(path), 'commit', '-m', 'ignore build output')
        result = self.finish(task, '--apply', '--validate', 'mkdir -p build; printf output > build/result; touch code.txt', '--cleanup')
        self.assertNotIn('blocked', result)
        self.assertEqual(result['validation']['state'], 'passed')
        self.assertEqual(result['cleanup']['inspection']['classification'], 'BLOCKED')
        self.assertTrue((path / 'build/result').exists())
        self.assertTrue(path.exists())

    def test_unchecked_ownership_and_directory_selection_refused(self):
        task, path = self.imported()
        (path / 'code.txt').write_text('mine')
        result = self.finish(task, '--apply', '--validate', 'true', '--file', 'code.txt', '--message', 'test')
        self.assertIn('blocked', result)
        result = self.finish(task, '--apply', '--file', '.', '--message', 'test', '--ownership-checked')
        self.assertIn('blocked', result)
        self.assertEqual(self.run_cmd('git', '-C', str(path), 'diff', '--cached').stdout, '')

    def test_finish_repair_shared_project_and_task_locks(self):
        import fcntl
        task, path, file = self.drift()
        token = self.obj('task', 'diagnose', 'secretary', task['id'])['snapshot']
        for lockpath in (self.repo / '.git/awo-dispatch.lock', file.with_suffix('.lock')):
            with lockpath.open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                before = file.read_bytes()
                for action in [('repair', '--snapshot', token), ('finish', '--validate', 'true')]:
                    result = self.cli('task', action[0], 'secretary', task['id'], '--apply', *action[1:], success=False)
                    self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, file.read_bytes())

    def test_finish_close_failure_is_pending_not_success(self):
        task, path = self.imported()
        (self.root / 'session').write_text(str(path))
        self.env.pop('ORCA_TERMINAL_HANDLE', None)
        self.env['TEST_TERMINALS'] = json.dumps({'terminals': [{'handle': 't1', 'worktreePath': str(path), 'agentIdentity': 'codex', 'connected': True}]})
        fake = self.root / 'bin/orca'
        fake.write_text(fake.read_text().replace("elif a[:2] == ['terminal', 'close']:", "elif a[:2] == ['terminal', 'close']:\n    sys.exit(1)"))
        result = self.finish(task, '--apply', '--validate', 'true', '--close', '--processes-checked', '--next', 'review')
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['finish']['session']['state'], 'unverified')
        self.assertEqual(result['session']['state'], 'present')
        self.assertTrue(path.exists())

    def inprocess_args(self, task, **overrides):
        import argparse
        values = dict(project='secretary', id=task['id'], action='finish', apply=True,
                      validate=['true'], validation=None, timeout=10, file=[], message=None,
                      owner_session=None, ownership_checked=False, close=False, cleanup=False,
                      next=None, input_checked=False, processes_checked=False, reconcile_commit=False)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_commit_receipt_interruption_unknown_then_explicit_reconcile(self):
        import os
        import sys
        from unittest.mock import patch
        from test_request import ROOT
        sys.path.insert(0, str(ROOT / 'scripts'))
        import awo_lifecycle as life
        import awo_completion as completion
        task, path = self.imported()
        (path / 'code.txt').write_text('owned current change')
        original_save = completion.audit.save
        def crash(file, tasks):
            if tasks[0].get('finish', {}).get('commit', {}).get('state') == 'committed':
                raise KeyboardInterrupt
            original_save(file, tasks)
        args = self.inprocess_args(task, file=['code.txt'], message='once', ownership_checked=True)
        with patch.dict(os.environ, self.env), patch.object(completion.audit, 'save', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                life.task_command(args)
        saved = self.obj('task', 'show', 'secretary', task['id'])
        self.assertEqual(saved['finish']['commit']['state'], 'attempting')
        head = self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout
        result = self.finish(task, '--apply', '--validate', 'true', '--file', 'code.txt', '--message', 'once', '--ownership-checked')
        self.assertIn('미확인', result['blocked'])
        self.assertEqual(head, self.run_cmd('git', '-C', str(path), 'rev-parse', 'HEAD').stdout)
        result = self.finish(task, '--apply', '--reconcile-commit')
        self.assertIn('대조 완료', result['blocked'])
        self.assertEqual(self.obj('task', 'show', 'secretary', task['id'])['finish']['commit']['state'], 'committed')
        self.assertNotIn('blocked', self.finish(task, '--apply', '--validate', 'true'))

    def test_repair_rechecks_snapshot_immediately_before_apply(self):
        import os
        import sys
        from unittest.mock import patch
        from test_request import ROOT
        sys.path.insert(0, str(ROOT / 'scripts'))
        import awo_repair as repair
        import awo_lifecycle as life
        task, path, file = self.drift()
        original = repair.diagnose
        with patch.dict(os.environ, self.env):
            first = original(str(self.repo), task)
            second = dict(first, snapshot='concurrent-change')
            args = self.inprocess_args(task, action='repair', snapshot=first['snapshot'])
            before = file.read_bytes()
            with patch.object(repair, 'diagnose', side_effect=[first, second]):
                with self.assertRaisesRegex(RuntimeError, '직전 snapshot'):
                    life.task_command(args)
            self.assertEqual(before, file.read_bytes())

    def test_commit_file_deletion_is_supported(self):
        task, path = self.imported()
        (path / 'code.txt').unlink()
        result = self.finish(task, '--apply', '--validate', 'true', '--file', 'code.txt', '--message', 'delete owned file', '--ownership-checked')
        self.assertNotIn('blocked', result)
        self.assertEqual(self.run_cmd('git', '-C', str(path), 'status', '--porcelain').stdout, '')
