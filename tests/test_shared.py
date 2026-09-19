import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_shared as shared

BODY = 'def helper():\n' + '    return 1\n' * 60


class SharedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repos = {}
        for name, files in {
            'a': {'lib/kakao_send.py': BODY, 'pricing/price_rules.py': BODY + '# a\n', 'a/helpers.py': BODY + '#1', 'pkg/__init__.py': BODY, '.claude/hooks/h.sh': BODY + 'h'},
            'b': {'tools/kakao_send.py': BODY, 'pricing/price_rules.py': BODY + '# b changed\n', 'b/helpers.py': BODY + '#2', 'x/__init__.py': BODY, '.claude/hooks/h.sh': BODY + 'h'},
        }.items():
            repo = self.root / name
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            for rel, text in files.items():
                (repo / rel).parent.mkdir(parents=True, exist_ok=True)
                (repo / rel).write_text(text)
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            self.repos[name] = str(repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_identical_and_diverged_copies(self):
        res = shared.scan([(n, p) for n, p in self.repos.items()])
        same = {g['name'] for g in res['identical']}
        diverged = {g['name'] for g in res['diverged']}
        self.assertEqual(same, {'lib/kakao_send.py'})
        self.assertEqual(diverged, {'pricing/price_rules.py'})  # a/helpers.py vs b/helpers.py differ by folder: not paired
        self.assertEqual(len(res['identical'][0]['copies']), 2)

    def test_generic_names_are_ignored(self):
        res = shared.scan([(n, p) for n, p in self.repos.items()])
        names = {g['name'] for g in res['identical'] + res['diverged']}
        self.assertNotIn('__init__.py', names)
        self.assertNotIn('h.sh', names)

    def test_single_repo_is_not_shared(self):
        res = shared.scan([('a', self.repos['a'])])
        self.assertEqual((res['identical'], res['diverged']), ([], []))


if __name__ == '__main__':
    unittest.main()
