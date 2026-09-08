#!/usr/bin/env python3
"""Read-only agent process inspection. Never collect full command arguments."""
import argparse
import json
import math
import os
import re
import subprocess


def elapsed_seconds(value):
    days, _, clock = value.rpartition('-')
    parts = [int(part) for part in clock.split(':')]
    if len(parts) not in (2, 3) or any(part < 0 for part in parts):
        raise ValueError('invalid elapsed time')
    return (int(days or 0) * 86400 + sum(part * scale for part, scale in
            zip(reversed(parts), (1, 60, 3600))))


def parse_processes(output, threshold_hours=24):
    sessions = []
    for line in output.splitlines():
        fields = line.strip().split(None, 4)
        if len(fields) != 5:
            continue
        pid, ppid, tty, elapsed, command = fields
        executable = os.path.basename(command)
        if not re.fullmatch(r'(?:claude|codex|codex-code-mode-host)', executable):
            continue
        try:
            seconds = elapsed_seconds(elapsed)
            sessions.append(dict(pid=int(pid), ppid=int(ppid), tty=tty,
                                 elapsed_seconds=seconds, executable=executable,
                                 stale=seconds >= threshold_hours * 3600))
        except ValueError:
            continue
    return sessions


def inspect_sessions(threshold_hours=24):
    result = subprocess.run(['ps', '-axo', 'pid=,ppid=,tty=,etime=,comm='],
                            check=True, capture_output=True, text=True)
    return parse_processes(result.stdout, threshold_hours)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--threshold-hours', type=float, default=24)
    args = parser.parse_args()
    if not math.isfinite(args.threshold_hours) or args.threshold_hours < 0:
        parser.error('threshold must be nonnegative')
    try:
        sessions = inspect_sessions(args.threshold_hours)
    except (OSError, subprocess.CalledProcessError):
        parser.exit(1, 'Unable to inspect agent sessions.\n')
    if args.json:
        print(json.dumps(sessions, indent=2))
    else:
        print('Read-only agent sessions (elapsed time does not prove inactivity):')
        for item in sessions:
            status = 'STALE_SESSION' if item['stale'] else 'RUNNING'
            print(f"{status} {item['executable']} pid={item['pid']} "
                  f"ppid={item['ppid']} tty={item['tty']} "
                  f"age={item['elapsed_seconds'] / 3600:.1f}h")
        if not sessions:
            print('No matching sessions.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
