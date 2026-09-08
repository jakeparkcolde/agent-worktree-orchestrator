"""Real Git cleanup regression tests; all repositories live in temporary folders."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CleanupRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.repo = self.home / 'main'
        self.repo.mkdir()
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.repo / 'code.txt').write_text('initial\n')
        (self.repo / '.gitignore').write_text('local-only/\n')
        self.git('add', '.')
        self.git('commit', '-m', 'initial')
        remote = self.home / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
        self.git('remote', 'add', 'origin', str(remote))
        self.git('push', '-u', 'origin', 'main')
        self.wt = self.home / 'task'
        self.git('worktree', 'add', '-b', 'task', str(self.wt))
        self.config = self.home / 'projects.yaml'
        self.config.write_text(f'projects:\n  test:\n    path: "{self.repo}"\n    base_ref: "origin/main"\n    max_worktrees: 3\n')
        self.state = self.repo / '.git/awo/worktrees.json'
        self.cli('audit', '--json')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def cli(self, command, *args):
        env = dict(os.environ, AWO_PROJECTS_FILE=str(self.config))
        return subprocess.run([sys.executable, str(ROOT / 'scripts/awo_audit.py'),
                               command, 'test', *args], env=env, capture_output=True, text=True)

    def age(self):
        old = time.time() - 200 * 3600
        data = json.loads(self.state.read_text())
        for meta in data.values():
            meta.update(first_seen_at=old, last_activity_at=old)
        self.state.write_text(json.dumps(data))
        gitdir = Path(subprocess.run(['git', '-C', str(self.wt), 'rev-parse', '--absolute-git-dir'],
                                     check=True, capture_output=True, text=True).stdout.strip())
        for name in ('HEAD', 'index', 'logs/HEAD'):
            path = gitdir / name
            if path.exists():
                os.utime(path, (old, old))

    def test_recent_apply_refuses(self):
        result = self.cli('cleanup', '--worktree', str(self.wt), '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.wt.exists())

    def test_exact_target_and_explicit_bulk(self):
        self.age()
        result = self.cli('cleanup', '--worktree', str(self.wt), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['worktrees'][0]['classification'], 'SAFE_CLEANUP')
        self.assertTrue(self.wt.exists())
        self.assertNotEqual(self.cli('cleanup', '--apply').returncode, 0)
        self.assertNotEqual(self.cli('cleanup', '--worktree', str(self.wt) + '-wrong', '--apply').returncode, 0)
        result = self.cli('cleanup', '--all-safe', '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.wt.exists())
        self.assertTrue(self.repo.exists())

    def test_targeted_apply_removes_only_selected_worktree(self):
        self.age()
        other = self.home / 'other'
        self.git('worktree', 'add', '-b', 'other', str(other))
        preview = self.cli('cleanup', '--all-safe', '--json')
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertTrue(self.wt.exists())
        result = self.cli('cleanup', '--worktree', str(self.wt), '--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.wt.exists())
        self.assertTrue(other.exists())

    def test_dirty_and_ignored_data_refuse(self):
        self.age()
        (self.wt / 'code.txt').write_text('changed\n')
        self.assertNotEqual(self.cli('cleanup', '--worktree', str(self.wt), '--apply').returncode, 0)
        (self.wt / 'code.txt').write_text('initial\n')
        (self.wt / 'local-only').mkdir()
        (self.wt / 'local-only/private.txt').write_text('private fixture\n')
        self.assertNotEqual(self.cli('cleanup', '--worktree', str(self.wt), '--apply').returncode, 0)
        self.assertEqual((self.wt / 'local-only/private.txt').read_text(), 'private fixture\n')

    def test_corrupted_metadata_refuses(self):
        for content in ('{broken', '[]', '{"bad": {"first_seen_at": NaN, "last_activity_at": NaN}}'):
            self.state.write_text(content)
            result = self.cli('cleanup', '--all-safe', '--apply')
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(self.wt.exists())

    def test_recreated_same_path_and_head_is_recent(self):
        self.age()
        self.git('worktree', 'remove', str(self.wt))
        self.git('worktree', 'add', str(self.wt), 'task')
        result = self.cli('cleanup', '--worktree', str(self.wt), '--apply', '--json')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(self.wt.exists())


if __name__ == '__main__':
    unittest.main()
