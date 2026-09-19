"""Request routing with real Git worktrees and a local Orca CLI test double."""
import json
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'repo'
        self.remote = self.root / 'origin.git'
        self.env = {**os.environ, 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'Test',
                    'GIT_COMMITTER_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid',
                    'GIT_COMMITTER_EMAIL': 'test@example.invalid'}
        self.run_cmd('git', 'init', '--bare', str(self.remote))
        self.run_cmd('git', 'init', '-b', 'main', str(self.repo))
        (self.repo / 'code.txt').write_text('initial\n')
        self.git('add', 'code.txt')
        self.git('commit', '-m', 'initial')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', '-u', 'origin', 'main')
        self.config = self.root / 'projects.yaml'
        self.config.write_text(f'projects:\n  secretary:\n    path: "{self.repo}"\n'
                               '    aliases: "나의 카카오 비서|카카오 비서"\n'
                               '    base_ref: "origin/main"\n    max_worktrees: 2\n')
        fake = self.root / 'bin'
        fake.mkdir()
        orca = fake / 'orca'
        orca.write_text('''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
a = sys.argv[1:]
repo = os.environ['TEST_REPO']
with open(os.environ['ORCA_CALLS'], 'a') as f: f.write(json.dumps(a) + '\\n')
if a[:2] == ['repo', 'list']:
    print(json.dumps({'ok': True, 'result': {'repos': [{'id': 'test', 'path': repo}]}}))
elif a[:2] == ['repo', 'set-base-ref']:
    print('{"ok": true}')
elif a[:2] == ['worktree', 'create']:
    if os.environ.get('ORCA_FAIL'):
        print('{"ok": false, "error": "unavailable"}')
        sys.exit(0)
    name = a[a.index('--name') + 1]
    base = a[a.index('--base-branch') + 1]
    path = str(pathlib.Path(repo).parent / name)
    subprocess.run(['git', '-C', repo, 'worktree', 'add', '-b', 'codex/' + name, path, base], check=True, capture_output=True)
    print(json.dumps({'ok': True, 'result': {'path': path}}))
else:
    sys.exit(2)
''')
        orca.chmod(0o755)
        self.calls = self.root / 'calls.jsonl'
        self.env.update(PATH=str(fake) + os.pathsep + os.environ['PATH'],
                        AWO_PROJECTS_FILE=str(self.config), TEST_REPO=str(self.repo),
                        ORCA_CALLS=str(self.calls))

    def run_cmd(self, *cmd, success=True):
        p = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        if success:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def git(self, *args):
        return self.run_cmd('git', '-C', str(self.repo), *args).stdout.strip()

    def request(self, *args, success=True, text='AWO 카카오 비서 관련 작업하고 싶다'):
        return self.run_cmd(str(ROOT / 'bin/awo'), 'request', text, *args, success=success)

    def report(self, *args, **kwargs):
        return json.loads(self.request(*args, **kwargs).stdout)

    def test_missing_goal_never_creates_even_with_apply(self):
        result = self.report('--apply')
        self.assertEqual(result['action'], 'needs_goal')
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.repo / '.git/awo').exists())

    def test_preview_is_read_only(self):
        result = self.report('--goal', '알림 누락 수정')
        self.assertEqual(result['action'], 'create')
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.repo / '.git/awo').exists())
        self.assertEqual(len(result['worktrees']), 1)

    def test_create_then_reuse_dirty_at_limit_without_launch(self):
        goal = '알림 누락 수정'
        first = self.report('--goal', goal, '--apply')
        wt = Path(first['path'])
        self.assertEqual(first['action'], 'create')
        self.assertNotEqual(wt, self.repo)
        self.assertEqual(self.git('rev-parse', 'main'), self.git('rev-parse', 'origin/main'))
        self.assertEqual(self.git('status', '--porcelain'), '')
        (wt / 'code.txt').write_text('unfinished user work\n')
        second = self.report('--goal', ' 알림   누락 수정 ', '--apply')
        self.assertEqual(second['action'], 'reuse')
        self.assertEqual(second['path'], str(wt))
        self.assertEqual((wt / 'code.txt').read_text(), 'unfinished user work\n')
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        creates = [a for a in calls if a[:2] == ['worktree', 'create']]
        self.assertEqual(len(creates), 1)
        self.assertIn('--no-parent', creates[0])
        self.assertNotIn('--agent', creates[0])
        self.assertEqual(creates[0][creates[0].index('--base-branch') + 1], 'origin/main')

    def test_alias_and_command_prefix_are_distinct(self):
        with self.config.open('a') as f:
            f.write(f'  awo:\n    path: "{self.repo}"\n    aliases: "오케스트레이터"\n')
        self.assertEqual(self.report()['project'], 'secretary')
        self.assertEqual(self.report(text='AWO 나의 카카오 비서관련 레포 작업')['project'], 'secretary')
        self.assertEqual(self.report(text='AWO 사용하고 싶다')['action'], 'needs_project')

    def test_ambiguous_and_unknown_project_do_not_mutate(self):
        with self.config.open('a') as f:
            f.write(f'  other:\n    path: "{self.repo}"\n    aliases: "카카오 비서"\n')
        result = self.report('--goal', '고치기', '--apply')
        self.assertEqual(result['action'], 'needs_project')
        self.assertEqual(set(result['candidates']), {'secretary', 'other'})
        self.assertEqual(self.report('--project', 'missing')['action'], 'needs_project')
        self.assertFalse(self.calls.exists())

    def test_existing_unregistered_work_requires_inspection_and_can_be_adopted(self):
        wt = self.root / 'existing'
        self.git('worktree', 'add', '-b', 'existing', str(wt))
        result = self.report('--goal', '알림 누락 수정', '--apply')
        self.assertEqual(result['action'], 'needs_worktree')
        self.assertFalse(self.calls.exists())
        result = self.report('--goal', '알림 누락 수정', '--worktree', str(wt), '--apply')
        self.assertEqual(result['action'], 'reuse')
        self.assertEqual(self.report('--goal', '알림 누락 수정')['path'], str(wt))
        self.assertFalse(self.calls.exists())
        blocked = self.report('--goal', '독립 목표', '--worktree', str(wt), '--apply', success=False)
        self.assertEqual(blocked['action'], 'blocked')

    def test_primary_or_foreign_path_cannot_be_adopted(self):
        for path in (self.repo, self.root):
            result = self.report('--goal', '수정', '--worktree', str(path), '--apply', success=False)
            self.assertEqual(result['action'], 'blocked')
        self.assertFalse(self.calls.exists())

    def test_in_progress_and_locked_worktree_block_reuse(self):
        first = self.report('--goal', '수정', '--apply')
        wt = Path(first['path'])
        self.git('worktree', 'lock', str(wt))
        self.assertEqual(self.report('--goal', '수정', '--apply', success=False)['action'], 'blocked')
        self.git('worktree', 'unlock', str(wt))
        gitdir = self.run_cmd('git', '-C', str(wt), 'rev-parse', '--absolute-git-dir').stdout.strip()
        (Path(gitdir) / 'MERGE_HEAD').write_text(self.git('rev-parse', 'HEAD'))
        self.assertEqual(self.report('--goal', '수정', '--apply', success=False)['action'], 'blocked')

    def test_limit_blocks_independent_goal(self):
        self.report('--goal', '첫 목표', '--apply')
        self.assertEqual(self.report('--goal', '독립 목표', '--apply', success=False)['action'], 'blocked')

    def test_orca_false_success_is_an_error_and_not_recorded(self):
        self.env['ORCA_FAIL'] = '1'
        p = self.request('--goal', '수정', '--apply', success=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('Orca refused', p.stderr)
        self.assertFalse((self.repo / '.git/awo/tasks.json').exists())

    def test_configured_non_main_base(self):
        self.git('branch', 'develop')
        self.git('checkout', 'develop')
        (self.repo / 'code.txt').write_text('develop only\n')
        self.git('commit', '-am', 'develop change')
        self.git('push', 'origin', 'develop')
        self.git('checkout', 'main')
        self.config.write_text(self.config.read_text().replace('origin/main', 'origin/develop'))
        result = self.report('--goal', '수정', '--apply')
        self.assertEqual(result['base_ref'], 'origin/develop')
        self.assertEqual(self.run_cmd('git', '-C', result['path'], 'rev-parse', 'HEAD').stdout.strip(),
                         self.git('rev-parse', 'origin/develop'))
        self.assertNotEqual(self.git('rev-parse', 'main'), self.git('rev-parse', 'origin/develop'))

    def test_new_goal_creates_only_after_existing_work_is_acknowledged(self):
        self.config.write_text(self.config.read_text().replace('max_worktrees: 2', 'max_worktrees: 3'))
        self.git('worktree', 'add', '-b', 'other', str(self.root / 'other'))
        result = self.report('--goal', '독립 작업', '--new-goal', '--apply')
        self.assertEqual(result['action'], 'create')
        self.assertEqual(len(result['worktrees']), 3)
        self.assertEqual(result['known_goals'][0]['path'], result['path'])

    def test_replaced_worktree_is_not_reused_from_stale_metadata(self):
        first = self.report('--goal', '수정', '--apply')
        self.git('worktree', 'remove', first['path'])
        self.git('worktree', 'add', '-b', 'different', first['path'], 'main')
        result = self.report('--goal', '수정', '--apply')
        self.assertEqual(result['action'], 'needs_worktree')
        self.assertEqual(result['known_goals'], [])

    def test_concurrent_request_lock_prevents_creation(self):
        folder = self.repo / '.git/awo'
        folder.mkdir()
        with (folder / 'tasks.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            p = self.request('--goal', '수정', '--apply', success=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('another AWO request', p.stderr)
        self.assertFalse(self.calls.exists())

    def test_local_only_repository_creates_and_reuses_from_explicit_local_base(self):
        self.git('remote', 'remove', 'origin')
        self.config.write_text(self.config.read_text().replace('origin/main', 'main'))
        first = self.report('--goal', '로컬 사이트 구축 재개', '--apply')
        self.assertEqual(first['action'], 'create')
        self.assertEqual(self.run_cmd('git', '-C', first['path'], 'rev-parse', 'HEAD').stdout.strip(),
                         self.git('rev-parse', 'main'))
        self.assertEqual(self.report('--goal', '로컬 사이트 구축 재개', '--apply')['action'], 'reuse')

    def test_existing_origin_fetch_failure_never_falls_back_to_local(self):
        self.git('remote', 'set-url', 'origin', str(self.root / 'missing.git'))
        self.config.write_text(self.config.read_text().replace('origin/main', 'main'))
        result = self.request('--goal', '수정', '--apply', success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_other_remote_is_not_mistaken_for_local_only(self):
        self.git('remote', 'rename', 'origin', 'upstream')
        self.config.write_text(self.config.read_text().replace('origin/main', 'main'))
        result = self.request('--goal', '수정', '--apply', success=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_corrupt_metadata_never_creates(self):
        folder = self.repo / '.git/awo'
        folder.mkdir()
        (folder / 'tasks.json').write_text('{}')
        self.assertNotEqual(self.request('--goal', '수정', '--apply', success=False).returncode, 0)
        self.assertFalse(self.calls.exists())


if __name__ == '__main__':
    unittest.main()
