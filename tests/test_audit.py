import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit', ROOT / 'scripts/awo_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.wt = self.root / 'work tree'
        self.git(self.root, 'init', '-q', str(self.repo))
        self.git(self.repo, 'config', 'user.email', 'test@example.invalid')
        self.git(self.repo, 'config', 'user.name', 'Test')
        (self.repo / 'source.txt').write_text('original\n')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'initial')
        self.git(self.repo, 'branch', '-M', 'main')
        self.git(self.repo, 'worktree', 'add', '-qb', 'task', str(self.wt))
        self.record = audit.records(self.repo)[1]
        self.meta = {'first_seen_at': time.time(), 'last_activity_at': time.time()}
        self.inspect()

    def git(self, path, *args):
        return subprocess.check_output(['git', '-C', str(path), *args], stderr=subprocess.DEVNULL).decode().strip()

    def inspect(self):
        return audit.inspect(str(self.wt), 'main', self.record, str(self.repo), self.meta, time.time(), (24, 72, 168))

    def age(self, hours):
        stamp = time.time() - hours * 3600
        self.meta.update(first_seen_at=stamp, last_activity_at=stamp)
        gd = Path(self.git(self.wt, 'rev-parse', '--absolute-git-dir'))
        for name in ('HEAD', 'index', 'logs/HEAD'):
            p = gd / name
            if p.exists():
                os.utime(p, (stamp, stamp))

    def test_age_gates(self):
        self.assertEqual(self.inspect()['classification'], 'ACTIVE')
        self.age(25)
        self.assertEqual(self.inspect()['classification'], 'ACTIVE_IDLE')
        self.age(73)
        self.assertEqual(self.inspect()['classification'], 'SAFE_CLEANUP')

    def test_hidden_modified_file(self):
        self.git(self.wt, 'update-index', '--assume-unchanged', 'source.txt')
        (self.wt / 'source.txt').write_text('private uncommitted fixture')
        self.age(200)
        self.assertEqual(self.inspect()['classification'], 'BLOCKED')

    def test_skip_worktree(self):
        self.git(self.wt, 'update-index', '--skip-worktree', 'source.txt')
        self.age(200)
        self.assertEqual(self.inspect()['classification'], 'BLOCKED')

    def test_locked_and_git_operation(self):
        self.record['locked'] = 'fixture'
        self.assertEqual(self.inspect()['classification'], 'BLOCKED')
        del self.record['locked']
        gd = Path(self.git(self.wt, 'rev-parse', '--absolute-git-dir'))
        (gd / 'MERGE_HEAD').write_text(self.git(self.wt, 'rev-parse', 'HEAD') + '\n')
        self.age(200)
        self.assertEqual(self.inspect()['classification'], 'BLOCKED')

    def test_tracked_runtime(self):
        (self.wt / 'usage-log.jsonl').write_text('{}\n')
        self.git(self.wt, 'add', '.')
        self.git(self.wt, 'commit', '-qm', 'runtime fixture')
        self.git(self.repo, 'merge', '--ff-only', 'task')
        self.inspect()
        self.age(200)
        self.assertEqual(self.inspect()['classification'], 'REVIEW')

    def test_tracked_artifacts(self):
        (self.wt / 'artifacts').mkdir()
        (self.wt / 'artifacts' / 'report.txt').write_text('fixture')
        self.git(self.wt, 'add', '.')
        self.git(self.wt, 'commit', '-qm', 'artifact')
        self.git(self.repo, 'merge', '--ff-only', 'task')
        self.inspect()
        self.age(200)
        self.assertEqual(self.inspect()['classification'], 'ARCHIVE')

    def test_patch_equivalence_is_not_topology(self):
        (self.wt / 'source.txt').write_text('changed\n')
        self.git(self.wt, 'commit', '-qam', 'task change')
        commit = self.git(self.wt, 'rev-parse', 'HEAD')
        self.git(self.repo, 'cherry-pick', commit)
        # Force a different commit identity without changing its patch.
        self.git(self.repo, 'commit', '--amend', '-qm', 'equivalent base')
        self.git(self.wt, 'branch', '--set-upstream-to=main')
        # Unpushed topology correctly blocks even patch-equivalent history.
        row = self.inspect()
        self.assertEqual(row['topology_unique'], 1)
        self.assertEqual(row['patch_unique'], 0)
        self.assertEqual(row['patch_equivalent'], 1)
        self.assertEqual(row['tree_diff_files'], 0)
        self.assertNotEqual(row['classification'], 'SAFE_CLEANUP')

    def test_final_tree_drift_retained(self):
        (self.repo / 'new.txt').write_text('base advance')
        self.git(self.repo, 'add', '.')
        self.git(self.repo, 'commit', '-qm', 'base advance')
        self.age(200)
        row = self.inspect()
        self.assertEqual(row['patch_unique'], 0)
        self.assertEqual(row['tree_diff_files'], 1)
        self.assertEqual(row['classification'], 'STALE')


if __name__ == '__main__':
    unittest.main()
