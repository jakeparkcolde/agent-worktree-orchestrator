import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_guard as guard


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / 'home'
        self.other = self.root / 'other'
        for repo in (self.home, self.other):
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        self.wt = self.root / 'other-wt'
        subprocess.run(['git', '-C', str(self.other), 'commit', '--allow-empty', '-qm', 'i'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@e', 'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@e'})
        subprocess.run(['git', '-C', str(self.other), 'worktree', 'add', '-qb', 'wt', str(self.wt)], check=True)
        cfg = self.root / 'projects.yaml'
        cfg.write_text(f'projects:\n  home:\n    path: "{self.home}"\n  other:\n    path: "{self.other}"\n')
        self.env = patch.dict(os.environ, {'AWO_PROJECTS_FILE': str(cfg), 'AWO_LEDGER_DIR': str(self.root / 'ledger')})
        self.env.start()
        os.environ.pop('AWO_GUARD', None)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def check(self, target, cwd=None, session='s1', tool='Edit'):
        payload = dict(session_id=session, cwd=str(cwd or self.home), tool_name=tool, tool_input={'file_path': str(target)})
        out = io.StringIO()
        code = guard.check_hook(io.StringIO(json.dumps(payload)), out)
        return code, (json.loads(out.getvalue()) if out.getvalue().strip() else None)

    def test_editing_another_projects_main_warns_once_per_session(self):
        code, msg = self.check(self.other / 'm.py')
        self.assertEqual(code, 0)
        self.assertIn('other', msg['systemMessage'])
        self.assertIn('awo start other', msg['hookSpecificOutput']['additionalContext'])
        self.assertIsNone(self.check(self.other / 'n.py')[1])
        self.assertIsNotNone(self.check(self.other / 'n.py', session='s2')[1])

    def test_own_repo_worktree_and_unregistered_paths_are_silent(self):
        self.assertIsNone(self.check(self.home / 'a.py')[1])
        self.assertIsNone(self.check(self.wt / 'a.py')[1])
        self.assertIsNone(self.check(self.root / 'loose.txt')[1])
        self.assertIsNone(self.check(self.other / 'x.py', tool='Read')[1])

    def test_block_mode_denies(self):
        with patch.dict(os.environ, {'AWO_GUARD': 'block'}):
            code, msg = self.check(self.other / 'm.py')
        self.assertEqual(msg['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_off_mode_and_garbage_are_silent(self):
        with patch.dict(os.environ, {'AWO_GUARD': 'off'}):
            self.assertIsNone(self.check(self.other / 'm.py')[1])
        out = io.StringIO()
        self.assertEqual(guard.check_hook(io.StringIO('nope'), out), 0)
        self.assertEqual(out.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
