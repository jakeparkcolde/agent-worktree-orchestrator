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
import awo_ledger as ledger


class LedgerBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'a.py').write_text('x')
        self.dir = self.root / 'ledger'
        self.env = patch.dict(os.environ, {'AWO_LEDGER_DIR': str(self.dir), 'ORCA_TERMINAL_HANDLE': 'term_1'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()


class RecordTests(LedgerBase):
    def hook(self, tool, **tool_input):
        payload = dict(session_id='s1', cwd=str(self.repo), tool_name=tool, tool_input=tool_input)
        return ledger.record_hook(io.StringIO(json.dumps(payload)))

    def test_edit_is_recorded_with_repo_and_terminal(self):
        self.hook('Edit', file_path=str(self.repo / 'a.py'))
        rows = ledger.load()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['agent'], row['session'], row['terminal'], row['repo'], row['rel']),
                         ('claude', 's1', 'term_1', str(self.repo), 'a.py'))

    def test_notebook_path_and_new_file_outside_git(self):
        self.hook('NotebookEdit', notebook_path=str(self.repo / 'n.ipynb'))
        self.hook('Write', file_path=str(self.root / 'loose.txt'))
        rows = ledger.load()
        self.assertEqual(rows[0]['rel'], 'n.ipynb')
        self.assertIsNone(rows[1]['repo'])

    def test_non_edit_tools_and_garbage_are_ignored(self):
        self.hook('Read', file_path=str(self.repo / 'a.py'))
        self.assertEqual(ledger.record_hook(io.StringIO('not json')), 0)
        self.assertEqual(ledger.load(), [])


class CodexTests(LedgerBase):
    def rollout(self, name, cwd, patches):
        path = self.root / 'codex' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps({'type': 'session_meta', 'timestamp': '2026-09-19T01:00:00Z', 'payload': {'id': 'cx1', 'cwd': cwd}})]
        for p in patches:
            lines.append(json.dumps({'type': 'response_item', 'timestamp': '2026-09-19T01:05:00Z',
                                     'payload': {'type': 'custom_tool_call', 'name': 'exec', 'input': p}}))
        path.write_text('\n'.join(lines) + '\n')
        return path

    def test_patch_paths_are_ingested_once(self):
        src = 'text(await tools.apply_patch("*** Begin Patch\\n*** Update File: a.py\\n@@\\n-x\\n+y\\n*** Add File: ' + str(self.repo / 'b.py') + '\\n+z\\n*** End Patch"))'
        self.rollout('r1.jsonl', str(self.repo), [src])
        self.assertEqual(ledger.ingest_codex(self.root / 'codex', days=30), 2)
        self.assertEqual(ledger.ingest_codex(self.root / 'codex', days=30), 0)
        rels = sorted(r['rel'] for r in ledger.load())
        self.assertEqual(rels, ['a.py', 'b.py'])
        self.assertTrue(all(r['agent'] == 'codex' and r['session'] == 'cx1' for r in ledger.load()))


class QueryTests(LedgerBase):
    def test_last_owner_wins_and_files_of_terminal(self):
        ledger.append(dict(ts=1, agent='claude', session='s1', terminal='t1', repo='/r', rel='x.py', path='/r/x.py'))
        ledger.append(dict(ts=2, agent='codex', session='s2', terminal='t2', repo='/r', rel='x.py', path='/r/x.py'))
        ledger.append(dict(ts=3, agent='claude', session='s1', terminal='t1', repo='/r', rel='y.py', path='/r/y.py'))
        owners = ledger.owners()
        self.assertEqual(owners[('/r', 'x.py')]['session'], 's2')
        self.assertEqual(sorted(ledger.files_of(terminal='t1')), [('/r', 'x.py'), ('/r', 'y.py')])
        self.assertEqual(ledger.touchers('/r', 'x.py'), {'s1', 's2'})


if __name__ == '__main__':
    unittest.main()
