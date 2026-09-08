"""Safe helper behavior without invoking launchctl or inspecting real processes."""
import importlib.util
from pathlib import Path
import plistlib
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sessions = load('awo_sessions')
launchd = load('awo_launchd')


class SessionTests(unittest.TestCase):
    def test_elapsed_day_and_hour(self):
        self.assertEqual(sessions.elapsed_seconds('2-03:04:05'), 183845)
        self.assertEqual(sessions.elapsed_seconds('12:34'), 754)

    def test_filters_non_agent_and_never_retains_paths(self):
        result = sessions.parse_processes('1 0 ?? 1-00:00:00 /private/name/codex\n'
                                         '2 1 ttys001 01:00 claude\n'
                                         '3 1 ?? 01:00 unrelated\n'
                                         '4 1 ?? 01:00 codex --secret value\n')
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]['stale'])
        self.assertFalse(result[1]['stale'])
        self.assertEqual(result[0]['executable'], 'codex')
        self.assertNotIn('/private', str(result))
        self.assertNotIn('secret', str(result))

    def test_invalid_threshold_rejected(self):
        for value in ('nan', 'inf', '-1'):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/awo_sessions.py'),
                                     '--threshold-hours', value], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_ps_uses_comm_not_arguments(self):
        with mock.patch.object(sessions.subprocess, 'run') as run:
            run.return_value.stdout = ''
            sessions.inspect_sessions()
        self.assertEqual(run.call_args.args[0], ['ps', '-axo', 'pid=,ppid=,tty=,etime=,comm='])


class LaunchdTests(unittest.TestCase):
    def test_calendar_and_safe_argument_encoding(self):
        payload = launchd.build_plist('com.awo.watch', '/tmp/path with spaces/awo',
                                      'name; echo secret', '/tmp/config with spaces', True)
        self.assertEqual(payload['ProgramArguments'],
                         [str(Path('/tmp/path with spaces/awo').resolve()), 'watch', 'name; echo secret', '--notify'])
        self.assertEqual(plistlib.loads(plistlib.dumps(payload)), payload)
        self.assertEqual([x['Hour'] for x in payload['StartCalendarInterval']], [9, 18])
        self.assertFalse(payload['RunAtLoad'])
        self.assertNotIn('StandardOutPath', payload)
        self.assertNotIn('StandardErrorPath', payload)

    def test_label_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            launchd.build_plist('../../other', '/tmp/awo', 'project')

    def test_install_defaults_to_preview(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/awo_launchd.py'),
                                 'install', 'example'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DRY RUN', result.stdout)
        self.assertIn('StartCalendarInterval', result.stdout)


if __name__ == '__main__':
    unittest.main()
