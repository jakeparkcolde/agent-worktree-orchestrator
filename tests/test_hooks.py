import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_hooks as hooks

EXISTING = {'hooks': {'PostToolUse': [{'matcher': '*', 'hooks': [{'type': 'command', 'command': 'orca-hook.sh'}]}]}, 'model': 'x'}


class HookTests(unittest.TestCase):
    def test_install_is_idempotent_and_keeps_existing(self):
        s = json.loads(json.dumps(EXISTING))
        self.assertEqual(hooks.install(s, Path('/opt/awo/bin/awo')), ['PostToolUse', 'PreToolUse'])
        self.assertEqual(hooks.install(s, Path('/opt/awo/bin/awo')), [])
        self.assertEqual(s['hooks']['PostToolUse'][0]['hooks'][0]['command'], 'orca-hook.sh')
        self.assertEqual(s['hooks']['PostToolUse'][1]['hooks'][0]['command'], '/opt/awo/bin/awo ledger record')
        self.assertEqual(s['model'], 'x')

    def test_uninstall_removes_only_awo(self):
        s = json.loads(json.dumps(EXISTING))
        hooks.install(s, Path('/opt/awo/bin/awo'))
        self.assertEqual(sorted(hooks.uninstall(s)), ['PostToolUse', 'PreToolUse'])
        self.assertEqual(s['hooks']['PostToolUse'], EXISTING['hooks']['PostToolUse'])
        self.assertEqual(s['hooks']['PreToolUse'], [])

    def test_cli_previews_then_applies_with_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'settings.json'
            path.write_text(json.dumps(EXISTING))
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / 'scripts/awo_hooks.py'), *a, '--settings', str(path),
                                             '--awo', str(ROOT / 'bin/awo')], capture_output=True, text=True)
            self.assertIn('DRY RUN', run('install').stdout)
            self.assertEqual(json.loads(path.read_text()), EXISTING)
            out = run('install', '--apply')
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(len(list(Path(tmp).glob('settings.json.awo-backup-*'))), 1)
            self.assertIn('installed', run('status').stdout)


if __name__ == '__main__':
    unittest.main()
