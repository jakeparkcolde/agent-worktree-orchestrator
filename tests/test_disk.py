"""Disk state, concurrency, CLI and launchd tests without real notifications/jobs."""
from contextlib import redirect_stdout
import fcntl
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import awo_disk as disk
import awo_disk_launchd as launchd


class TransitionTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [('normal', 5 * disk.GB - 1, 'critical'),
                 ('normal', 5 * disk.GB, 'warning'),
                 ('normal', 10 * disk.GB - 1, 'warning'),
                 ('normal', 10 * disk.GB, 'normal'),
                 ('warning', 15 * disk.GB - 1, 'warning'),
                 ('critical', 15 * disk.GB - 1, 'critical'),
                 ('warning', 15 * disk.GB, 'normal'),
                 ('critical', 15 * disk.GB, 'normal')]
        for previous, free, expected in cases:
            with self.subTest(previous=previous, free=free):
                self.assertEqual(disk.next_level(previous, free), expected)

    def test_hysteresis_and_escalation(self):
        level = 'normal'
        levels = []
        for gb in (20, 9, 11, 4, 6, 10, 14, 15, 9):
            level = disk.next_level(level, gb * disk.GB)
            levels.append(level)
        self.assertEqual(levels, ['normal', 'warning', 'warning', 'critical',
                                  'critical', 'critical', 'critical', 'normal', 'warning'])

    def test_custom_thresholds(self):
        self.assertEqual(disk.next_level('normal', 19 * disk.GB, 20, 8, 25), 'warning')
        self.assertEqual(disk.next_level('normal', 7 * disk.GB, 20, 8, 25), 'critical')
        self.assertEqual(disk.next_level('critical', 25 * disk.GB, 20, 8, 25), 'normal')

    def test_invalid_thresholds(self):
        for values in ((5, 5, 15), (10, 0, 15), (10, -1, 15), (10, 5, 10),
                       (float('nan'), 5, 15), (10, 5, float('inf'))):
            with self.subTest(values=values), self.assertRaises(ValueError):
                disk.validate_thresholds(*values)


class DiskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()
        self.state_dir = self.path / 'state'
        self.target = self.state_dir / (disk.path_key(self.path) + '.json')
        platform = mock.patch.object(disk.sys, 'platform', 'darwin')
        platform.start()
        self.addCleanup(platform.stop)
        notification = mock.patch.object(disk, 'notify_macos')
        self.notification = notification.start()
        self.addCleanup(notification.stop)

    def scan(self, gb, notify=True, path=None):
        with mock.patch.object(disk.shutil, 'disk_usage', return_value=mock.Mock(free=int(gb * disk.GB))):
            return disk.check_disk(path or self.path, self.state_dir, notify=notify)

    def test_persisted_transitions_only_across_checks(self):
        reports = [self.scan(gb) for gb in (20, 9, 9, 11, 4, 4, 6, 14, 15, 16)]
        self.assertEqual([r['level'] for r in reports if r['notified']], ['warning', 'critical', 'normal'])
        self.assertEqual(self.notification.call_count, 3)
        state = json.loads(self.target.read_text())
        self.assertEqual(state['level'], 'normal')
        self.assertEqual(state['path'], str(self.path))

    def test_initial_critical_and_state_saved_before_notification(self):
        def observe(report):
            self.assertEqual(json.loads(self.target.read_text())['level'], 'critical')
        self.notification.side_effect = observe
        self.assertTrue(self.scan(4)['notified'])
        self.assertFalse(self.scan(4)['notified'])

    def test_preview_does_not_consume_transition_or_create_state(self):
        self.assertTrue(self.scan(4, notify=False)['transition'])
        self.assertFalse(self.state_dir.exists())
        self.notification.assert_not_called()
        self.assertTrue(self.scan(4)['notified'])
        original = self.target.read_bytes()
        self.assertTrue(self.scan(20, notify=False)['transition'])
        self.assertEqual(self.target.read_bytes(), original)
        self.assertTrue(self.scan(20)['notified'])

    def test_notification_failure_is_reported_and_not_retried(self):
        self.notification.side_effect = subprocess.TimeoutExpired('osascript', 15)
        report = self.scan(4)
        self.assertIn('will not be retried', report['notification_error'])
        self.assertFalse(report['notified'])
        self.assertFalse(self.scan(4)['transition'])
        self.notification.assert_called_once()

    def test_state_write_failure_does_not_notify_or_destroy_previous(self):
        self.scan(20)
        original = self.target.read_bytes()
        with mock.patch.object(disk.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.scan(4)
        self.notification.assert_not_called()
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(list(self.state_dir.glob('.disk-*')), [])

    def test_missing_path_or_measurement_failure_preserves_state(self):
        self.scan(9)
        original = self.target.read_bytes()
        with self.assertRaises(FileNotFoundError):
            self.scan(20, path=self.path / 'missing')
        with mock.patch.object(disk.shutil, 'disk_usage', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                disk.check_disk(self.path, self.state_dir, notify=True)
        self.assertEqual(self.target.read_bytes(), original)
        self.notification.assert_called_once()

    def test_invalid_state_is_preserved_without_notification(self):
        self.state_dir.mkdir()
        for invalid in ('{broken', '[]', '{"version": 2}',
                        json.dumps({'version': 1, 'path': str(self.path), 'level': 'bogus'}),
                        json.dumps({'version': 1, 'path': '/other', 'level': 'normal'})):
            self.target.write_text(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.scan(4)
            self.assertEqual(self.target.read_text(), invalid)
        self.notification.assert_not_called()

    def test_paths_are_independent_and_symlink_aliases_share_state(self):
        other = self.path / 'other'
        other.mkdir()
        alias = self.path / 'alias'
        alias.symlink_to(other)
        self.assertTrue(self.scan(4)['notified'])
        self.assertTrue(self.scan(4, path=other)['notified'])
        self.assertFalse(self.scan(4, path=alias)['notified'])
        self.assertEqual(len(list(self.state_dir.glob('*.json'))), 2)

    def test_concurrent_process_is_refused_while_lock_is_held(self):
        self.state_dir.mkdir()
        with (self.state_dir / (disk.path_key(self.path) + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code = ('import sys; sys.path.insert(0, sys.argv[1]); import awo_disk; '
                    'awo_disk.sys.platform="darwin"; '
                    'awo_disk.check_disk(sys.argv[2], sys.argv[3], notify=True)')
            result = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts'),
                                     str(self.path), str(self.state_dir)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('already running', result.stderr)
        self.assertFalse(self.target.exists())
        self.assertTrue(self.scan(4)['notified'])

    def test_non_macos_notification_refused_without_state(self):
        with mock.patch.object(disk.sys, 'platform', 'linux'), self.assertRaises(ValueError):
            self.scan(4)
        self.assertFalse(self.state_dir.exists())


class CLITests(unittest.TestCase):
    def test_process_restarts_reuse_persisted_state(self):
        code = '''
import json, sys
from unittest import mock
sys.path.insert(0, sys.argv[1])
import awo_disk
awo_disk.sys.platform = 'darwin'
with mock.patch.object(awo_disk.shutil, 'disk_usage', return_value=mock.Mock(free=4 * awo_disk.GB)):
    with mock.patch.object(awo_disk, 'notify_macos'):
        print(json.dumps(awo_disk.check_disk(sys.argv[2], sys.argv[3], notify=True)))
'''
        with tempfile.TemporaryDirectory() as directory:
            command = [sys.executable, '-c', code, str(ROOT / 'scripts'), directory, str(Path(directory) / 'state')]
            first = json.loads(subprocess.check_output(command, text=True))
            second = json.loads(subprocess.check_output(command, text=True))
        self.assertTrue(first['notified'])
        self.assertFalse(second['notified'])
        self.assertEqual(second['level'], 'critical')

    def test_real_disk_preview_via_cli_without_project_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state'
            result = subprocess.run([str(ROOT / 'bin/awo'), 'disk', 'check', directory,
                                     '--state-dir', str(state), '--json'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertGreaterEqual(report['free_bytes'], 0)
            self.assertEqual(report['mode'], 'preview')
            self.assertFalse(report['notified'])
            self.assertFalse(state.exists())

    def test_invalid_cli_options_fail(self):
        for options in (['check', '--warning-gb', 'nan'], ['check', '--critical-gb', '20'],
                        ['launchd', 'install', '--interval-seconds', '0'],
                        ['launchd', 'install', '--interval-seconds', '1.5']):
            result = subprocess.run([str(ROOT / 'bin/awo'), 'disk', *options], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)

    def test_notification_failure_cli_returns_error_with_json(self):
        report = {'notification_error': 'failed', 'notified': False}
        with mock.patch.object(disk, 'check_disk', return_value=report), redirect_stdout(io.StringIO()) as output:
            with mock.patch.object(disk.sys, 'stderr', new=io.StringIO()):
                self.assertEqual(disk.main(['check', '--notify', '--json']), 1)
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_notification_uses_literal_arguments(self):
        path = '/tmp/quotes"; do shell script "touch BAD"\n$(touch BAD)'
        with mock.patch.object(disk.subprocess, 'run') as run:
            disk.notify_macos({'level': 'warning', 'free_gb': 9, 'path': path})
        argv = run.call_args.args[0]
        self.assertEqual(argv[:3], ['/usr/bin/osascript', '-e', disk.NOTIFICATION_SCRIPT])
        self.assertIn(path, argv[3])
        self.assertNotIn(path, argv[2])
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['timeout'], 15)


class LaunchdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.args = mock.Mock(action='install', apply=True, awo=str(ROOT / 'bin/awo'),
                              path=str(self.home), state_dir=str(self.home / 'state'),
                              warning_gb=10, critical_gb=5, recovery_gb=15, interval_seconds=300)
        self.payload = launchd.build_plist(self.args.awo, self.args.path, self.args.state_dir)
        self.target = self.home / 'Library/LaunchAgents' / (self.payload['Label'] + '.plist')
        for patcher in (mock.patch.object(launchd.Path, 'home', return_value=self.home),
                        mock.patch.object(launchd.sys, 'platform', 'darwin')):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(launchd.subprocess, 'run')
        self.run = patcher.start()
        self.addCleanup(patcher.stop)

    def manage(self):
        with redirect_stdout(io.StringIO()) as output:
            result = launchd.manage_job(self.args)
        self.assertEqual(result, 0)
        return output.getvalue()

    def test_plist_interval_namespace_and_literal_arguments(self):
        path = str(self.home / 'space & quote"; $value')
        payload = launchd.build_plist('/tmp/space dir/awo', path, self.args.state_dir, 20, 8, 25, 60)
        self.assertEqual(plistlib.loads(plistlib.dumps(payload)), payload)
        self.assertTrue(payload['Label'].startswith('com.awo.disk.'))
        self.assertNotEqual(payload['Label'], self.payload['Label'])
        self.assertEqual(payload['ProgramArguments'][:5],
                         [str(Path('/tmp/space dir/awo').resolve()), 'disk', 'check', path, '--notify'])
        self.assertIn('20.0', payload['ProgramArguments'])
        self.assertEqual(payload['StartInterval'], 60)
        self.assertTrue(payload['RunAtLoad'])
        self.assertNotIn('StartCalendarInterval', payload)
        self.assertNotIn('AWO_PROJECTS_FILE', payload['EnvironmentVariables'])

    def test_preview_has_no_side_effects(self):
        self.args.apply = False
        self.assertIn('DRY RUN', self.manage())
        self.run.assert_not_called()
        self.assertFalse(self.target.parent.exists())
        self.assertFalse(Path(self.args.state_dir).exists())

    def test_install_and_uninstall_leave_watch_job_and_state(self):
        self.target.parent.mkdir(parents=True)
        watch = self.target.parent / 'com.awo.watch.plist'
        watch.write_text('existing worktree watch')
        state = Path(self.args.state_dir)
        state.mkdir()
        (state / 'keep').write_text('persisted')
        self.manage()
        self.assertEqual(plistlib.loads(self.target.read_bytes()), self.payload)
        self.assertEqual(self.run.call_args.args[0][1], 'bootstrap')
        self.args.action = 'uninstall'
        self.manage()
        self.assertEqual(self.run.call_args.args[0][1], 'bootout')
        self.assertFalse(self.target.exists())
        self.assertEqual(watch.read_text(), 'existing worktree watch')
        self.assertEqual((state / 'keep').read_text(), 'persisted')

    def test_existing_job_and_mismatched_uninstall_preserved(self):
        self.manage()
        original = self.target.read_bytes()
        with self.assertRaises(ValueError):
            self.manage()
        self.args.action = 'uninstall'
        self.args.interval_seconds = 600
        with self.assertRaises(ValueError):
            self.manage()
        self.assertEqual(self.target.read_bytes(), original)

    def test_bootstrap_failure_rolls_back_and_bootout_failure_preserves(self):
        self.run.side_effect = subprocess.CalledProcessError(1, 'launchctl')
        with self.assertRaises(subprocess.CalledProcessError):
            self.manage()
        self.assertFalse(self.target.exists())
        self.run.side_effect = None
        self.manage()
        self.args.action = 'uninstall'
        self.run.side_effect = subprocess.CalledProcessError(1, 'launchctl')
        with self.assertRaises(subprocess.CalledProcessError):
            self.manage()
        self.assertTrue(self.target.exists())

    def test_symlink_and_non_macos_refused(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.home / 'missing')
        for action in ('install', 'uninstall'):
            self.args.action = action
            with self.assertRaises(ValueError):
                self.manage()
        self.assertTrue(self.target.is_symlink())
        with mock.patch.object(launchd.sys, 'platform', 'linux'), self.assertRaises(ValueError):
            self.manage()
        self.run.assert_not_called()

    def test_corrupt_plist_is_preserved(self):
        self.target.parent.mkdir(parents=True)
        self.args.action = 'uninstall'
        for content in (b'broken', b'<?xml version="1.0"?><plist><dict>'):
            self.target.write_bytes(content)
            with self.assertRaises(ValueError):
                self.manage()
            self.assertEqual(self.target.read_bytes(), content)
        self.run.assert_not_called()

    def test_uninstall_after_watched_directory_disappears(self):
        watched = self.home / 'mountpoint'
        watched.mkdir()
        self.args.path = str(watched)
        self.manage()
        watched.rmdir()
        self.args.action = 'uninstall'
        self.manage()
        self.assertEqual(self.run.call_args.args[0][1], 'bootout')


if __name__ == '__main__':
    unittest.main()
