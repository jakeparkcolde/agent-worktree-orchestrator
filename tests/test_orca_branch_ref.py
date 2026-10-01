"""Regression: Orca reports a terminal's branch as a full ref (refs/heads/<name>).

Terminal verification must treat 'refs/heads/worker' and 'worker' as the same
branch; otherwise every new worker launch is reported as unverified even though
the agent started in the right worktree.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_start as start


class OrcaFullBranchRefTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        for args in (('config', 'user.email', 'test@example.com'), ('config', 'user.name', 'Test'),
                     ('commit', '--allow-empty', '-qm', 'initial')):
            subprocess.run(['git', '-C', str(self.repo), *args], check=True, capture_output=True)
        self.wt = self.root / 'worker'
        subprocess.run(['git', '-C', str(self.repo), 'worktree', 'add', '-qb', 'worker', str(self.wt)],
                       check=True, capture_output=True)
        self.args = start.argparse.Namespace(new_session=False, project='test', task='worker', agent='claude',
                                             goal='Brand intro motion graphic', worktree=str(self.wt))

    def tearDown(self):
        self.temp.cleanup()

    def test_full_branch_ref_from_orca_is_confirmed(self):
        observed = {'handle': 't1', 'worktreePath': str(self.wt), 'branch': 'refs/heads/worker',
                    'connected': True, 'agentIdentity': 'claude'}
        answers = [{'result': {'terminals': []}}, {'result': {'terminal': {'handle': 't1'}}},
                   {'result': {'terminal': observed}}]
        with patch.object(start, 'orca', side_effect=answers):
            value, code = start.launch(self.args, self.repo, 'HEAD', 'claude', 'worker')
        self.assertEqual(value['awo_dispatch']['state'], 'session_confirmed', value['awo_dispatch'].get('reason'))
        self.assertEqual(code, 0)


if __name__ == '__main__':
    unittest.main()
