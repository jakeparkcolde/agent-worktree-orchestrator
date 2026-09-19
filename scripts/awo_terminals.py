#!/usr/bin/env python3
"""Inventory Orca terminals of one project and close only provably finished ones.

Default is read-only. `--close-safe` previews closable terminals; `--apply`
closes them. Live agents are reported, never closed. A plain shell is closable
only when its screen ends at an idle prompt, so shells running services stay.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from awo_audit import config, records

ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07')
PROMPT = re.compile(r'[%$#]\s*$')
EXIT_HINTS = ('Resume this session with', 'codex resume')
DUPLICATE_HINT = 'is open in another app'
CLOSABLE = {'EXITED', 'DUPLICATE', 'IDLE_SHELL'}


def last_line(preview):
    lines = [line.rstrip() for line in ANSI.sub('', preview or '').splitlines() if line.strip()]
    return lines[-1] if lines else ''


# @MX:ANCHOR: safety contract — every close decision flows through classify().
def classify(term, now_ms, threshold_hours, self_handle):
    handle = term.get('handle')
    preview = ANSI.sub('', term.get('preview') or '')
    tail = preview[-800:]
    agent = term.get('agentIdentity') or None
    last = term.get('lastOutputAt')
    idle = max(0.0, (now_ms - last) / 3_600_000) if isinstance(last, (int, float)) and last > 0 else None
    at_prompt = bool(PROMPT.search(last_line(preview)))
    row = dict(handle=handle, path=str(term.get('worktreePath') or ''), title=term.get('title') or '',
               agent=agent, idle_hours=None if idle is None else round(idle, 1), closable=False)
    if handle and handle == self_handle:
        state, reason = 'SELF', 'the terminal running this command'
    elif idle is None:
        state, reason = 'UNKNOWN', 'no activity time reported'
    elif agent and any(h in tail for h in EXIT_HINTS) and at_prompt:
        state, reason = 'EXITED', 'agent exited; only its shell remains'
    elif agent and DUPLICATE_HINT in tail:
        state, reason = 'DUPLICATE', 'blocked because the conversation is open elsewhere'
    elif agent:
        state, reason = ('IDLE_AGENT', 'live agent with no recent output; not closed') if idle >= threshold_hours else ('WORKING', 'recent agent output')
    elif at_prompt:
        state, reason = 'IDLE_SHELL', 'plain shell waiting at a prompt'
    else:
        state, reason = 'BUSY_SHELL', 'plain shell not at a prompt (may run a service)'
    row.update(state=state, reason=reason,
               closable=state in CLOSABLE and idle is not None and idle >= threshold_hours)
    return row


def inventory(paths, listing, now_ms, threshold_hours, self_handle):
    result = listing.get('result', listing) if isinstance(listing, dict) else {}
    items = result.get('terminals') if isinstance(result, dict) else None
    if not isinstance(items, list):
        raise RuntimeError('Orca returned no terminal list')
    rows = [classify(t, now_ms, threshold_hours, self_handle) for t in items
            if isinstance(t, dict) and str(t.get('worktreePath') or '') in paths]
    working = {}
    for r in rows:
        if r['state'] in ('WORKING', 'SELF') and r['agent']:
            working.setdefault(r['path'], []).append(r['handle'])
    warnings = [f'{path}: {len(hs)} agents working in the same checkout; commits may mix'
                for path, hs in sorted(working.items()) if len(hs) > 1]
    return dict(rows=rows, warnings=warnings, truncated=bool(result.get('truncated')))


def close_safe(rows, show, close, now_ms, threshold_hours, self_handle):
    results = []
    for row in rows:
        if not row['closable']:
            continue
        try:
            fresh = classify(show(row['handle']), now_ms, threshold_hours, self_handle)
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
            results.append(dict(row, result='skipped_unverifiable'))
            continue
        if not fresh['closable'] or fresh['state'] != row['state']:
            results.append(dict(row, result='skipped_changed'))
            continue
        try:
            close(row['handle'])
            results.append(dict(row, result='closed'))
        except (RuntimeError, OSError, subprocess.SubprocessError, ValueError):
            results.append(dict(row, result='close_failed'))
    return results


def orca(*args):
    p = subprocess.run(['orca', *args, '--json'], capture_output=True, text=True, timeout=40)
    if p.returncode:
        raise RuntimeError('Orca command failed: ' + ' '.join(args[:2]))
    value = json.loads(p.stdout)
    if not isinstance(value, dict) or value.get('ok') is False:
        raise RuntimeError('Unexpected Orca response')
    return value


def show_terminal(handle):
    value = orca('terminal', 'show', '--terminal', handle)
    result = value.get('result', value)
    term = result.get('terminal', result) if isinstance(result, dict) else None
    if not isinstance(term, dict) or term.get('handle') != handle:
        raise RuntimeError('Terminal metadata mismatch')
    return term


def project_paths(project):
    primary = Path(config(project, 'path')).expanduser().resolve()
    return {r['worktree'] for r in records(primary)}


def report(inv, results, apply, close_safe_flag):
    order = ['SELF', 'WORKING', 'IDLE_AGENT', 'EXITED', 'DUPLICATE', 'IDLE_SHELL', 'BUSY_SHELL', 'UNKNOWN']
    rows = sorted(inv['rows'], key=lambda r: (r['path'], order.index(r['state'])))
    print(f"Orca terminals: {len(rows)} (read-only unless --apply)")
    for r in rows:
        idle = '?' if r['idle_hours'] is None else f"{r['idle_hours']}h"
        mark = ' *' if r['closable'] else ''
        print(f"{r['state']:<11} idle={idle:<7} {r['agent'] or '-':<7} {r['path']}  {r['title'][:50]}{mark}")
    for w in inv['warnings']:
        print('WARNING ' + w)
    candidates = [r for r in rows if r['closable']]
    if close_safe_flag and not apply:
        print(f"{len(candidates)} closable (*). Re-run with --apply to close them.")
    elif not close_safe_flag and candidates:
        print(f"{len(candidates)} closable (*). Preview with --close-safe.")
    for r in results:
        print(f"{r['result']:<21} {r['handle']} {r['title'][:50]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--threshold-hours', type=float, default=12)
    parser.add_argument('--close-safe', action='store_true', help='select exited, duplicate and idle-shell terminals')
    parser.add_argument('--apply', action='store_true', help='with --close-safe, actually close them')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.threshold_hours) or args.threshold_hours <= 0:
        parser.error('threshold must be positive')
    if args.apply and not args.close_safe:
        parser.error('--apply requires --close-safe')
    try:
        paths = project_paths(args.project)
        now = int(time.time() * 1000)
        self_handle = os.environ.get('ORCA_TERMINAL_HANDLE')
        inv = inventory(paths, orca('terminal', 'list'), now, args.threshold_hours, self_handle)
        results = []
        if args.apply:
            if inv['truncated']:
                raise RuntimeError('Terminal listing is truncated; refusing to close anything')
            results = close_safe(inv['rows'], show_terminal,
                                 lambda h: orca('terminal', 'close', '--terminal', h),
                                 now, args.threshold_hours, self_handle)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print('ERROR: ' + (str(exc) if isinstance(exc, RuntimeError) else 'Unable to inspect Orca terminals'), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(dict(inv, results=results), ensure_ascii=False, indent=2))
    else:
        report(inv, results, args.apply, args.close_safe)
    return 0


if __name__ == '__main__':
    sys.exit(main())
