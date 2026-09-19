#!/usr/bin/env python3
"""Work ledger: which agent session touched which file in which repository.

Claude sessions append through a PostToolUse hook (`awo ledger record`).
Codex sessions are ingested from their rollout files (`awo ledger ingest-codex`).
The ledger lives in AWO_LEDGER_DIR (default ~/.awo/ledger) as monthly JSONL.
Recording is fail-open: a hook failure never blocks the agent.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

EDIT_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit'}
PATCH_PATH = re.compile(r'\*\*\* (?:Add|Update|Delete) File: (.+?)(?:\\n|\n|"|$)|\*\*\* Move to: (.+?)(?:\\n|\n|"|$)')


def ledger_dir():
    return Path(os.environ.get('AWO_LEDGER_DIR') or Path.home() / '.awo' / 'ledger')


def repo_of(path):
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.is_file():
        probe = probe.parent
    try:
        p = subprocess.run(['git', '-C', str(probe), 'rev-parse', '--show-toplevel'],
                           capture_output=True, text=True, timeout=5,
                           env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    except (OSError, subprocess.SubprocessError):
        return None
    return str(Path(p.stdout.strip()).resolve()) if p.returncode == 0 and p.stdout.strip() else None


def entry(agent, session, path, cwd, tool, ts=None, terminal=None):
    path = Path(path) if Path(path).is_absolute() else Path(cwd or '.') / path
    path = Path(os.path.normpath(str(path)))
    repo = repo_of(path)
    rel = None
    if repo:
        try:
            rel = str(path.resolve().relative_to(repo)) if path.exists() else str(path.relative_to(repo))
        except ValueError:
            rel = str(path)
    return dict(ts=ts if ts is not None else time.time(), agent=agent, session=session,
                terminal=terminal, cwd=cwd, repo=repo, rel=rel, path=str(path), tool=tool)


def append(row):
    target = ledger_dir()
    target.mkdir(parents=True, exist_ok=True)
    month = datetime.fromtimestamp(row.get('ts') or time.time(), timezone.utc).strftime('%Y-%m')
    line = (json.dumps(row, ensure_ascii=False) + '\n').encode('utf-8')
    fd = os.open(str(target / (month + '.jsonl')), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def load():
    rows = []
    for f in sorted(ledger_dir().glob('*.jsonl')):
        for line in f.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    rows.sort(key=lambda r: r.get('ts') or 0)
    return rows


def record_hook(stream):
    """Claude PostToolUse hook entry. Always returns 0."""
    try:
        payload = json.loads(stream.read())
        tool = payload.get('tool_name')
        if tool not in EDIT_TOOLS:
            return 0
        ti = payload.get('tool_input') or {}
        path = ti.get('file_path') or ti.get('notebook_path')
        if not path:
            return 0
        append(entry('claude', payload.get('session_id'), path, payload.get('cwd'), tool,
                     terminal=os.environ.get('ORCA_TERMINAL_HANDLE')))
    except Exception:  # fail-open by contract: never break the agent
        pass
    return 0


def iso_ts(value):
    try:
        return datetime.strptime(value[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return time.time()


def ingest_codex(root=None, days=3):
    root = Path(root or Path.home() / '.codex' / 'sessions')
    state_path = ledger_dir() / 'codex-ingest.json'
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
    cutoff = time.time() - days * 86400
    added = 0
    for f in sorted(root.rglob('*.jsonl')) if root.exists() else []:
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_mtime < cutoff:
            continue
        done = state.get(str(f), 0)
        if st.st_size <= done:
            continue
        session = cwd = None
        with f.open('rb') as stream:
            for raw in stream:
                try:
                    o = json.loads(raw)
                except ValueError:
                    continue
                p = o.get('payload') or {}
                if o.get('type') == 'session_meta':
                    session, cwd = p.get('id'), p.get('cwd')
                    continue
                if stream.tell() <= done:
                    continue
                if o.get('type') != 'response_item' or p.get('type') not in ('function_call', 'custom_tool_call', 'local_shell_call'):
                    continue
                text = p.get('input') or p.get('arguments') or ''
                if not isinstance(text, str) or '*** Begin Patch' not in text:
                    continue
                seen = set()
                for m in PATCH_PATH.finditer(text):
                    path = (m.group(1) or m.group(2) or '').strip()
                    if path and path not in seen:
                        seen.add(path)
                        append(entry('codex', session, path, cwd, 'apply_patch', ts=iso_ts(o.get('timestamp'))))
                        added += 1
        state[str(f)] = st.st_size
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state))
    os.replace(tmp, state_path)
    return added


def owners(rows=None):
    """(repo, rel) -> latest ledger row for that file."""
    result = {}
    for row in rows if rows is not None else load():
        if row.get('repo') and row.get('rel'):
            result[(row['repo'], row['rel'])] = row
    return result


def touchers(repo, rel, rows=None):
    return {r.get('session') for r in (rows if rows is not None else load())
            if r.get('repo') == repo and r.get('rel') == rel}


def files_of(terminal=None, session=None, rows=None):
    out = set()
    for r in rows if rows is not None else load():
        if (terminal and r.get('terminal') == terminal) or (session and r.get('session') == session):
            if r.get('repo') and r.get('rel'):
                out.add((r['repo'], r['rel']))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('record', help='Claude PostToolUse hook (reads JSON on stdin)')
    ing = sub.add_parser('ingest-codex')
    ing.add_argument('--days', type=float, default=3)
    who = sub.add_parser('who', help='who last touched a file')
    who.add_argument('path')
    ses = sub.add_parser('files', help='files touched by a session or terminal')
    ses.add_argument('--session')
    ses.add_argument('--terminal')
    args = parser.parse_args()
    if args.cmd == 'record':
        return record_hook(sys.stdin)
    if args.cmd == 'ingest-codex':
        print(f'ingested {ingest_codex(days=args.days)} codex file edits')
        return 0
    if args.cmd == 'who':
        e = entry(None, None, os.path.abspath(args.path), os.getcwd(), None)
        rows = [r for r in load() if r.get('repo') == e['repo'] and r.get('rel') == e['rel']]
        for r in rows[-10:]:
            when = datetime.fromtimestamp(r['ts']).strftime('%m-%d %H:%M')
            print(f"{when} {r.get('agent')} session={r.get('session')} terminal={r.get('terminal')}")
        if not rows:
            print('no ledger record')
        return 0
    if not (args.session or args.terminal):
        parser.error('files needs --session or --terminal')
    for repo, rel in sorted(files_of(args.terminal, args.session)):
        print(f'{repo}  {rel}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
