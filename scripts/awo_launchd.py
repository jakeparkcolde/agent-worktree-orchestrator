#!/usr/bin/env python3
"""Preview or explicitly install/uninstall a per-user macOS watch job."""
import argparse
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys


def build_plist(label, executable, project, config=None, notify=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]+', label):
        raise ValueError('label must contain only letters, digits, dots and hyphens')
    args = [str(Path(executable).expanduser().resolve()), 'watch', project]
    if notify:
        args.append('--notify')
    result = {'Label': label, 'ProgramArguments': args,
              'StartCalendarInterval': [{'Hour': 9, 'Minute': 0},
                                        {'Hour': 18, 'Minute': 0}],
              'RunAtLoad': False,
              'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'}}
    if config:
        result['EnvironmentVariables']['AWO_PROJECTS_FILE'] = str(Path(config).expanduser().resolve())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('project', help='use the original project for uninstall')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--label', default='com.awo.watch')
    parser.add_argument('--awo', default=str(Path(__file__).resolve().parent.parent / 'bin/awo'))
    parser.add_argument('--config')
    parser.add_argument('--notify', action='store_true')
    args = parser.parse_args()
    if args.action == 'install' and not args.project:
        parser.error('install requires a project')
    try:
        payload = build_plist(args.label, args.awo, args.project or '', args.config, args.notify)
    except ValueError as error:
        parser.error(str(error))
    target = Path.home() / 'Library/LaunchAgents' / (args.label + '.plist')
    if not args.apply:
        print(f'DRY RUN: {args.action} {target}')
        if args.action == 'install':
            print(plistlib.dumps(payload).decode())
        return 0
    if sys.platform != 'darwin':
        parser.error('--apply is supported only on macOS')
    domain = f'gui/{os.getuid()}'
    try:
        if args.action == 'install':
            if target.exists() or target.is_symlink():
                parser.error('job file already exists; uninstall it explicitly first')
            if not os.access(payload['ProgramArguments'][0], os.X_OK):
                parser.error('awo executable is missing or not executable')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                plistlib.dump(payload, stream)
            try:
                subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
            except (OSError, subprocess.CalledProcessError):
                target.unlink()
                raise
        else:
            if not target.exists():
                print('Job is not installed.')
                return 0
            if target.is_symlink():
                parser.error('refusing to remove a symlink')
            with target.open('rb') as stream:
                existing = plistlib.load(stream)
            if existing != payload:
                parser.error('job does not match these options; supply the original project/config/notify options')
            subprocess.run(['launchctl', 'bootout', domain, str(target)], check=True)
            target.unlink()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Launchd operation failed: {error}\n')
    print(f'{args.action}: {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
