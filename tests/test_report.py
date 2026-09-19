import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_ledger as ledger
import awo_report as report


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True, text=True).stdout


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.remote = self.root / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.remote)], check=True)
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(self.repo)], check=True, capture_output=True)
        git(self.repo, 'config', 'user.email', 't@e.com')
        git(self.repo, 'config', 'user.name', 'T')
        git(self.repo, 'checkout', '-q', '-b', 'main')
        (self.repo / 'a.py').write_text('1')
        git(self.repo, 'add', 'a.py')
        git(self.repo, 'commit', '-qm', 'init')
        git(self.repo, 'push', '-q', '-u', 'origin', 'main')
        self.env = patch.dict(os.environ, {'AWO_LEDGER_DIR': str(self.root / 'ledger')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def own(self, rel, session, terminal):
        ledger.append(dict(ts=1, agent='claude', session=session, terminal=terminal,
                           repo=str(self.repo), rel=rel, path=str(self.repo / rel)))

    def test_dirty_files_are_grouped_by_owner(self):
        (self.repo / 'a.py').write_text('2')
        (self.repo / 'new.py').write_text('n')
        (self.repo / 'mystery.txt').write_text('?')
        self.own('a.py', 's1', 'term_live')
        self.own('new.py', 's2', 'term_gone')
        st = report.checkout_state(str(self.repo), 'origin/main', ledger.owners(), {'term_live'})
        groups = {g['session']: g for g in st['owners']}
        self.assertEqual(groups['s1']['files'], ['a.py'])
        self.assertTrue(groups['s1']['alive'])
        self.assertFalse(groups['s2']['alive'])
        self.assertEqual(groups[None]['files'], ['mystery.txt'])
        self.assertEqual(st['dirty'], 3)

    def test_runtime_files_are_separated_from_unknown(self):
        (self.repo / '.orca').mkdir()
        (self.repo / '.orca' / 'state.json').write_text('{}')
        (self.repo / 'debug.log').write_text('x')
        st = report.checkout_state(str(self.repo), 'origin/main', {}, set())
        self.assertEqual([g['session'] for g in st['owners']], ['__runtime__'])
        self.assertEqual(sorted(st['owners'][0]['files']), ['.orca/', 'debug.log'])

    def test_untracked_directory_is_attributed_by_prefix(self):
        (self.repo / 'pkg').mkdir()
        (self.repo / 'pkg' / 'm.py').write_text('m')
        self.own('pkg/m.py', 's3', None)
        st = report.checkout_state(str(self.repo), 'origin/main', ledger.owners(), set())
        self.assertEqual([g['session'] for g in st['owners']], ['s3'])

    def test_unpushed_and_behind_counts(self):
        (self.repo / 'b.py').write_text('b')
        git(self.repo, 'add', 'b.py')
        git(self.repo, 'commit', '-qm', 'local')
        st = report.checkout_state(str(self.repo), 'origin/main', {}, set())
        self.assertEqual((st['unpushed'], st['ahead'], st['behind'], st['dirty']), (1, 1, 0, 0))

    def test_clean_checkout_renders_nothing_to_do(self):
        st = report.checkout_state(str(self.repo), 'origin/main', {}, set())
        text = report.render_markdown({'generated': 'now', 'checkouts': [dict(st, project='p')], 'warnings': [], 'errors': []})
        self.assertIn('정리할 것 없음', text)

    def test_markdown_lists_owner_and_unknown(self):
        (self.repo / 'a.py').write_text('3')
        self.own('a.py', 's1', 'term_live')
        (self.repo / 'z.txt').write_text('z')
        st = report.checkout_state(str(self.repo), 'origin/main', ledger.owners(), set())
        text = report.render_markdown({'generated': 'now', 'checkouts': [dict(st, project='p')],
                                       'warnings': ['/x: 2 agents working in the same checkout; commits may mix'], 'errors': []})
        self.assertIn('주인 모름', text)
        self.assertIn('s1', text)
        self.assertIn('동시 작업', text)

    def test_projects_are_read_from_config(self):
        cfg = self.root / 'projects.yaml'
        cfg.write_text('projects:\n  one:\n    path: "/a"\n    base_ref: "main"\n  two:\n    path: "/b"\n')
        self.assertEqual(report.project_list(cfg), [('one', '/a', 'main'), ('two', '/b', 'origin/main')])


if __name__ == '__main__':
    unittest.main()
