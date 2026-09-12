"""Independent per-path disk LaunchAgents; existing worktree watch jobs are untouched."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from xml.parsers.expat import ExpatError

from awo_disk import path_key, validate_thresholds


def build_plist(executable, path, state_dir, warning=10, critical=5, recovery=15, interval=300):
    validate_thresholds(warning, critical, recovery)
    if type(interval) is not int or interval < 1:
        raise ValueError('interval-seconds must be a positive integer')
    # Non-strict resolution also lets users uninstall after a volume is removed.
    path = Path(path).expanduser().resolve()
    args = [str(Path(executable).expanduser().resolve()), 'disk', 'check', str(path),
            '--notify', '--warning-gb', str(float(warning)), '--critical-gb', str(float(critical)),
            '--recovery-gb', str(float(recovery)), '--state-dir', str(Path(state_dir).expanduser().resolve())]
    return {'Label': 'com.awo.disk.' + path_key(path), 'ProgramArguments': args,
            'StartInterval': interval, 'RunAtLoad': True,
            'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}


def manage_job(args):
    payload = build_plist(args.awo, args.path, args.state_dir, args.warning_gb,
                          args.critical_gb, args.recovery_gb, args.interval_seconds)
    target = Path.home() / 'Library/LaunchAgents' / (payload['Label'] + '.plist')
    if not args.apply:
        print(f'DRY RUN: {args.action} {target}')
        if args.action == 'install':
            print(plistlib.dumps(payload).decode())
        return 0
    if sys.platform != 'darwin':
        raise ValueError('--apply is supported only on macOS')
    domain = f'gui/{os.getuid()}'
    if args.action == 'install':
        Path(payload['ProgramArguments'][3]).resolve(strict=True)
        if target.exists() or target.is_symlink():
            raise ValueError('disk job file already exists; uninstall it explicitly first')
        if not os.access(payload['ProgramArguments'][0], os.X_OK):
            raise ValueError('awo executable is missing or not executable')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            plistlib.dump(payload, stream)
        try:
            subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(target)], check=True)
        except (OSError, subprocess.SubprocessError):
            target.unlink()
            raise
    else:
        if target.is_symlink():
            raise ValueError('refusing to remove a symlink')
        if not target.exists():
            print('Disk job is not installed.')
            return 0
        try:
            with target.open('rb') as stream:
                existing = plistlib.load(stream)
        except (plistlib.InvalidFileException, ExpatError) as error:
            raise ValueError('invalid disk job plist; preserve and inspect it') from error
        if existing != payload:
            raise ValueError('disk job does not match; supply original path/threshold/state-dir/interval/awo options')
        subprocess.run(['/bin/launchctl', 'bootout', domain, str(target)], check=True)
        target.unlink()
    print(f'{args.action}: {target}')
    return 0
