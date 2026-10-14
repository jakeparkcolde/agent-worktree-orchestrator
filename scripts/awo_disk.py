#!/usr/bin/env python3
"""Host disk checks with persistent, transition-only macOS notifications."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

GB = 1_000_000_000
LEVELS = ('normal', 'warning', 'critical')
NOTIFICATION_SCRIPT = ('on run argv\n'
                       'display notification (item 1 of argv) with title "AWO disk"\n'
                       'end run')


def default_state_dir():
    return Path.home() / 'Library/Application Support/AWO/disk-watch'


def path_key(path):
    return hashlib.sha256(os.fsencode(str(path))).hexdigest()


def validate_thresholds(warning, critical, recovery):
    if not all(math.isfinite(x) for x in (warning, critical, recovery)):
        raise ValueError('disk thresholds must be finite')
    if not 0 < critical < warning < recovery:
        raise ValueError('require 0 < critical-gb < warning-gb < recovery-gb')


def next_level(previous, free_bytes, warning=10, critical=5, recovery=15):
    """Latch the highest severity until recovery, avoiding threshold flapping."""
    if free_bytes >= recovery * GB:
        return 'normal'
    if free_bytes < critical * GB or previous == 'critical':
        return 'critical'
    if free_bytes < warning * GB or previous == 'warning':
        return 'warning'
    return 'normal'


def load_state(target, path):
    try:
        state = json.loads(target.read_text())
    except FileNotFoundError:
        return None
    if (not isinstance(state, dict) or state.get('version') != 1
            or state.get('path') != str(path) or state.get('level') not in LEVELS):
        raise ValueError(f'invalid disk state: {target}; preserve and inspect it')
    return state


def save_state(target, state):
    """Replace a complete state atomically; do not notify if persistence fails."""
    fd, name = tempfile.mkstemp(prefix='.disk-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def notify_macos(report):
    label = {'normal': 'Recovered', 'warning': 'Warning', 'critical': 'Critical'}[report['level']]
    message = f"{label}: {report['free_gb']:.2f} GB free at {report['path']}"
    # Path/message are data, never interpolated into AppleScript or a shell.
    subprocess.run(['/usr/bin/osascript', '-e', NOTIFICATION_SCRIPT, message],
                   check=True, capture_output=True, text=True, timeout=15)


def check_disk(path, state_dir, warning=10, critical=5, recovery=15, notify=False):
    validate_thresholds(warning, critical, recovery)
    if notify and sys.platform != 'darwin':
        raise ValueError('--notify requires macOS')
    path = Path(path).expanduser().resolve(strict=True)
    state_dir = Path(state_dir).expanduser().resolve()
    target = state_dir / (path_key(path) + '.json')

    def scan():
        previous = load_state(target, path)
        free = shutil.disk_usage(path).free
        old_level = previous['level'] if previous else 'normal'
        level = next_level(old_level, free, warning, critical, recovery)
        changed = old_level != level
        report = {'path': str(path), 'free_bytes': free, 'free_gb': free / GB,
                  'previous_level': old_level, 'level': level, 'transition': changed,
                  'mode': 'notify' if notify else 'preview', 'notified': False,
                  'state_file': str(target),
                  'thresholds_gb': {'warning': warning, 'critical': critical, 'recovery': recovery}}
        if notify:
            # Commit before sending: a crash or ambiguous delivery must not cause
            # the same transition to be sent again on every launchd invocation.
            save_state(target, {'version': 1, 'path': str(path), 'level': level,
                                'free_bytes': free, 'checked_at': time.time(),
                                'thresholds_gb': report['thresholds_gb']})
            if changed:
                try:
                    notify_macos(report)
                    report['notified'] = True
                except (OSError, subprocess.SubprocessError) as error:
                    report['notification_error'] = (
                        f'notification failed ({type(error).__name__}); '
                        'transition was saved and will not be retried')
        return report

    if not notify:
        return scan()
    state_dir.mkdir(parents=True, exist_ok=True)
    # Keep the lock inode across invocations; unlinking permits parallel locks.
    with (state_dir / (path_key(path) + '.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('a disk check for this path is already running') from error
        return scan()


def add_disk_options(parser):
    parser.add_argument('path', nargs='?', default='/', help='existing path on the target filesystem (default: /)')
    parser.add_argument('--warning-gb', type=float, default=10)
    parser.add_argument('--critical-gb', type=float, default=5)
    parser.add_argument('--recovery-gb', type=float, default=15)
    parser.add_argument('--state-dir', default=str(default_state_dir()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='one scan; read-only unless --notify is supplied')
    add_disk_options(check)
    check.add_argument('--notify', action='store_true', help='persist state and notify on transitions (macOS)')
    check.add_argument('--json', action='store_true')
    launchd = commands.add_parser('launchd', help='separate periodic disk LaunchAgent; preview by default')
    launchd.add_argument('action', choices=['install', 'uninstall'])
    add_disk_options(launchd)
    launchd.add_argument('--interval-seconds', type=int, default=300)
    launchd.add_argument('--apply', action='store_true')
    launchd.add_argument('--awo', default=str(Path(__file__).resolve().parent.parent / 'bin/awo'))
    args = parser.parse_args(argv)
    try:
        validate_thresholds(args.warning_gb, args.critical_gb, args.recovery_gb)
        if args.command == 'launchd':
            from awo_disk_launchd import manage_job
            return manage_job(args)
        report = check_disk(args.path, args.state_dir, args.warning_gb,
                            args.critical_gb, args.recovery_gb, args.notify)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"{report['mode']}: {report['level']} — {report['free_gb']:.2f} GB free at {report['path']}")
            print(f"transition={report['transition']} notified={report['notified']}")
        if 'notification_error' in report:
            print('ERROR: ' + report['notification_error'], file=sys.stderr)
            return 1
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
