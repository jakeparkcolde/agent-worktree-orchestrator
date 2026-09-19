#!/usr/bin/env python3
"""Install or remove AWO's Claude Code hooks in a settings file (default ~/.claude/settings.json).

PostToolUse -> `awo ledger record` (work ledger); PreToolUse -> `awo guard`
(cross-project edit warning). Preview by default; --apply writes after
saving a timestamped backup. Existing hooks are preserved and never duplicated.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import time

MATCHER = 'Edit|Write|MultiEdit|NotebookEdit'
MARK = {'PostToolUse': 'ledger record', 'PreToolUse': 'guard'}


def command(awo, event):
    return f'{shlex.quote(str(awo))} {MARK[event]}'


def is_awo(hook, event):
    return isinstance(hook, dict) and str(hook.get('command', '')).endswith(' ' + MARK[event]) and 'awo' in str(hook.get('command', ''))


def install(settings, awo):
    hooks = settings.setdefault('hooks', {})
    changed = []
    for event in MARK:
        groups = hooks.setdefault(event, [])
        if any(is_awo(h, event) for g in groups if isinstance(g, dict) for h in g.get('hooks', [])):
            continue
        groups.append({'matcher': MATCHER, 'hooks': [{'type': 'command', 'command': command(awo, event), 'timeout': 10}]})
        changed.append(event)
    return changed


def uninstall(settings):
    changed = []
    for event in MARK:
        groups = settings.get('hooks', {}).get(event, [])
        kept = []
        for g in groups:
            if not isinstance(g, dict):
                kept.append(g)
                continue
            rest = [h for h in g.get('hooks', []) if not is_awo(h, event)]
            if len(rest) != len(g.get('hooks', [])):
                changed.append(event)
            if rest:
                kept.append(dict(g, hooks=rest))
        if groups:
            settings['hooks'][event] = kept
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall', 'status'])
    parser.add_argument('--settings', default=str(Path.home() / '.claude' / 'settings.json'))
    parser.add_argument('--awo', default=str(Path(__file__).resolve().parent.parent / 'bin' / 'awo'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = Path(args.settings).expanduser()
    try:
        settings = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except ValueError:
        parser.exit(1, f'refusing to touch unparsable settings: {path}\n')
    if args.action == 'status':
        for event in MARK:
            found = [h['command'] for g in settings.get('hooks', {}).get(event, []) if isinstance(g, dict)
                     for h in g.get('hooks', []) if is_awo(h, event)]
            print(f"{event}: {'installed -> ' + found[0] if found else 'not installed'}")
        return 0
    if args.action == 'install' and not os.access(args.awo, os.X_OK):
        parser.exit(1, f'awo executable not found: {args.awo}\n')
    changed = install(settings, Path(args.awo).resolve()) if args.action == 'install' else uninstall(settings)
    if not changed:
        print('nothing to change')
        return 0
    if not args.apply:
        print(f'DRY RUN: would {args.action} {", ".join(changed)} hooks in {path}')
        for event in changed:
            print(f'  {event} [{MATCHER}] -> {command(Path(args.awo).resolve(), event)}')
        return 0
    if path.exists():
        backup = path.with_name(path.name + time.strftime('.awo-backup-%Y%m%d-%H%M%S'))
        shutil.copy2(path, backup)
        print(f'backup: {backup}')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.awo-tmp')
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)
    print(f'{args.action}ed: {", ".join(changed)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
