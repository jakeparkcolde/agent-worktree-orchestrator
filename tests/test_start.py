import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_start as start


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.g('config', 'user.email', 'test@example.com')
        self.g('config', 'user.name', 'Test')
        self.g('commit', '--allow-empty', '-qm', 'initial')
        self.wt = self.root / 'worker'
        self.g('worktree', 'add', '-qb', 'worker', str(self.wt))
        self.args = start.argparse.Namespace(new_session=False, project='test', task='worker', agent='codex', goal='Implement $(false) safely', worktree=str(self.wt))

    def tearDown(self):
        self.temp.cleanup()

    def g(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True, text=True)

    def test_primary_rejected(self):
        with self.assertRaises(RuntimeError):
            start.validate_worktree(self.repo, self.repo)

    def test_foreign_rejected(self):
        with self.assertRaises(RuntimeError):
            start.validate_worktree(self.repo, self.root)

    def test_existing_terminal_not_duplicated(self):
        with patch.object(start, 'orca', return_value={'result': {'terminals': [{'handle': 'old'}]}}) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 3)
        self.assertEqual(value['awo_dispatch']['state'], 'existing_terminal')
        self.assertEqual(call.call_count, 1)

    def test_reuse_launch_bound_and_quoted(self):
        answers = [{'result': {'terminals': []}}, {'result': {'terminal': {'handle': 't1'}}},
                   {'result': {'terminal': {'handle': 't1', 'worktreePath': str(self.wt), 'branch': 'worker', 'connected': True, 'agentIdentity': 'codex'}}}]
        with patch.object(start, 'orca', side_effect=answers) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 0)
        self.assertEqual(value['awo_dispatch']['state'], 'session_confirmed')
        argv = call.call_args_list[1].args
        self.assertIn('path:' + str(self.wt), argv)
        self.assertEqual(start.shlex.split(argv[-1]), ['codex', '--', self.args.goal])
        self.assertNotIn('started', value['awo_dispatch']['state'])

    def test_wrong_agent_unverified(self):
        answers = [{'terminals': []}, {'terminal': {'handle': 't1'}},
                   {'terminal': {'handle': 't1', 'worktreePath': str(self.wt), 'branch': 'worker', 'connected': True, 'agentIdentity': 'claude'}}]
        with patch.object(start, 'orca', side_effect=answers[:2] + [answers[-1]] * 6), patch.object(start.time, 'sleep'):
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 3)
        self.assertEqual(value['awo_dispatch']['state'], 'unverified')

    def test_truncated_terminal_list_refused(self):
        with patch.object(start, 'orca', return_value={'terminals': [], 'truncated': True}) as call:
            with self.assertRaises(RuntimeError):
                start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(call.call_count, 1)

    def test_creation_timeout_is_uncertain_no_retry(self):
        with patch.object(start, 'orca', side_effect=[{'terminals': []}, subprocess.TimeoutExpired('hidden', 40)]) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 3)
        self.assertEqual(call.call_count, 2)
        self.assertIn('unknown', value['awo_dispatch']['reason'])

    def test_new_worktree_explicit_independent_options(self):
        self.args.worktree = None
        self.args.task = 'new-task'
        new = self.root / 'new'
        real_run = subprocess.run
        def fake_run(argv, **kw):
            if 'fetch' in argv or str(argv[0]).endswith('orca-repo-id.sh'):
                return subprocess.CompletedProcess(argv, 0, 'repo-id\n', '')
            return real_run(argv, **kw)
        def fake_orca(*argv):
            if argv[:2] == ('worktree', 'create'):
                self.g('worktree', 'add', '-qb', 'new-task', str(new))
                return {'result': {'worktree': {'path': str(new)}, 'startupTerminal': {'handle': 'new-handle'}}}
            return {'terminal': {'handle': 'new-handle', 'worktreePath': str(new), 'branch': 'new-task', 'connected': True, 'agentIdentity': 'codex'}}
        with patch.object(start, 'config', return_value='4'), patch.object(start.subprocess, 'run', side_effect=fake_run), patch.object(start, 'orca', side_effect=fake_orca) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'new-task')
        self.assertEqual(code, 0)
        argv = call.call_args_list[0].args
        self.assertIn('--no-parent', argv)
        self.assertIn('--base-branch', argv)
        self.assertEqual(argv[argv.index('--setup') + 1], 'run')
        self.assertEqual(argv[argv.index('--prompt') + 1], self.args.goal)
        self.assertEqual(value['awo_dispatch']['branch'], 'new-task')

    def test_explicit_new_session_with_unknown_terminal(self):
        self.args.new_session = True
        answers = [{'terminals': [{'handle': 'shell'}]}, {'terminal': {'handle': 't1'}},
                   {'terminal': {'handle': 't1', 'worktreePath': str(self.wt), 'branch': 'worker', 'connected': True, 'agentIdentity': 'codex'}}]
        with patch.object(start, 'orca', side_effect=answers) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 0)
        self.assertIn('warning', value['awo_dispatch'])
        self.assertEqual(call.call_count, 3)

    def test_explicit_new_session_cannot_duplicate_known_agent(self):
        self.args.new_session = True
        with patch.object(start, 'orca', return_value={'terminals': [{'handle': 'agent', 'agentIdentity': 'codex'}]}) as call:
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 3)
        self.assertEqual(call.call_count, 1)

    def test_malformed_terminal_and_handle_are_unverified(self):
        for metadata in (None, [], {'handle': 123}, {}):
            with self.subTest(metadata=metadata), patch.object(start, 'orca', side_effect=[{'terminals': []}, {'terminal': metadata}]) as call:
                value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
                self.assertEqual(code, 3)
                self.assertEqual(value['awo_dispatch']['path'], str(self.wt))
                self.assertEqual(call.call_count, 2)

    def test_wrong_terminal_path_is_unverified(self):
        answers = [{'terminals': []}, {'terminal': {'handle': 't1'}},
                   {'terminal': {'handle': 't1', 'worktreePath': str(self.repo), 'branch': 'worker', 'connected': True, 'agentIdentity': 'codex'}}]
        with patch.object(start, 'orca', side_effect=answers):
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 3)

    def test_no_goal_is_idle(self):
        self.args.goal = ''
        answers = [{'terminals': []}, {'terminal': {'handle': 't1'}},
                   {'terminal': {'handle': 't1', 'worktreePath': str(self.wt), 'branch': 'worker', 'connected': True, 'agentIdentity': 'codex'}}]
        with patch.object(start, 'orca', side_effect=answers):
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 0)
        self.assertEqual(value['awo_dispatch']['state'], 'idle')

    def test_new_session_requires_worktree_cli(self):
        result = subprocess.run([str(ROOT / 'bin/awo'), 'start', 'test', 'task', '--new-session'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--new-session requires --worktree', result.stderr)

    def test_json_failure_rejected(self):
        p = subprocess.CompletedProcess([], 0, json.dumps({'ok': False}), '')
        with patch.object(start.subprocess, 'run', return_value=p):
            with self.assertRaises(RuntimeError):
                start.orca('terminal', 'list')


if __name__ == '__main__':
    unittest.main()
