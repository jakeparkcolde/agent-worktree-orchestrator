"""Failure reproductions for durable dispatch ownership."""
from unittest.mock import patch
from test_start import DispatchTests
import awo_start as start


class DurableDispatchTests(DispatchTests):
    def test_interrupted_dispatch_blocks_next_process_attempt(self):
        def cfg(p, f, d=None):
            return {'path': str(self.repo), 'base_ref': 'HEAD'}.get(f, d)
        def interrupted(*a, before_create):
            before_create()
            raise KeyboardInterrupt
        with patch.object(start, 'config', side_effect=cfg), patch.object(start, 'launch', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                start.dispatch(self.args)
        with patch.object(start, 'config', side_effect=cfg), patch.object(start, 'launch') as launch:
            with self.assertRaises(RuntimeError):
                start.dispatch(self.args)
            launch.assert_not_called()

    def test_full_ref_terminal_branch_is_same_identity(self):
        answers = [{'terminals': []}, {'terminal': {'handle': 't1'}},
                   {'terminal': {'handle': 't1', 'worktreePath': str(self.wt),
                                 'branch': 'refs/heads/worker', 'connected': True,
                                 'agentIdentity': 'codex'}}]
        with patch.object(start, 'orca', side_effect=answers):
            value, code = start.launch(self.args, self.repo, 'HEAD', 'codex', 'worker')
        self.assertEqual(code, 0)
        self.assertEqual(value['awo_dispatch']['state'], 'session_confirmed')

    def test_preflight_duplicate_name_does_not_poison_project(self):
        from awo_state import pending
        self.args.worktree = None
        def cfg(p, f, d=None):
            return {'path': str(self.repo), 'base_ref': 'HEAD'}.get(f, d)
        with patch.object(start, 'config', side_effect=cfg), patch.object(start, 'orca') as orca:
            with self.assertRaises(RuntimeError):
                start.dispatch(self.args)
            orca.assert_not_called()
        self.assertIsNone(pending(self.repo))

    def test_preflight_missing_base_does_not_poison_project(self):
        from awo_state import pending
        self.args.worktree = None
        self.args.task = 'new-work'
        def cfg(p, f, d=None):
            return {'path': str(self.repo), 'base_ref': 'missing-local-ref', 'max_worktrees': '9'}.get(f, d)
        with patch.object(start, 'config', side_effect=cfg), patch.object(start, 'orca') as orca:
            with self.assertRaises(RuntimeError):
                start.dispatch(self.args)
            orca.assert_not_called()
        self.assertIsNone(pending(self.repo))
