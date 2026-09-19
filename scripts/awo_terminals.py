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
import secrets
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


# ---- retire: close one terminal only after its own work is committed ----

RETIRE_PROMPT = (
    '[AWO 창 정리 요청 {nonce}] 이 창을 닫기 전에 마무리해 주세요. · '
    '1) 이 대화에서 결정했지만 아직 저장하지 않은 것(메모리·노트·이어 붙이기 메시지)을 이 프로젝트 규칙대로 저장하세요. · '
    '2) 이 세션이 직접 고친 파일만 저장소별로 커밋하세요. 경로를 하나씩 지정해 git add 하고 git add -A, git add ., git commit -a 는 쓰지 마세요. '
    '다른 창이 고쳤거나 확실하지 않은 파일은 커밋하지 말고 남겨 두세요. · '
    '3) 푸시, 브랜치 삭제, 되돌리기 같은 다른 git 작업은 하지 마세요. · '
    '4) 작업 장부에 이 창이 고친 것으로 남은 미커밋 파일: {files} · '
    '5) 끝나면 마지막 줄 하나만 이렇게 쓰세요: AWO-RETIRE {nonce} 뒤에 DONE(마무리됨) 또는 BLOCKED(못 끝냄)와 짧은 이유.'
)
LIVE = {'WORKING', 'IDLE_AGENT'}
DEAD = {'EXITED', 'DUPLICATE', 'IDLE_SHELL'}


def select(rows, selector):
    hits = [r for r in rows if r['handle'] == selector]
    hits = hits or [r for r in rows if str(r['handle']).startswith(selector) or selector in (r['title'] or '')]
    if len(hits) != 1:
        names = ', '.join(f"{r['handle'][:13]} {r['title'][:30]}" for r in hits) or 'none'
        raise RuntimeError(f'selector must match exactly one terminal (matched: {names})')
    return hits[0]


def parse_retire(text, nonce):
    found = None
    for m in re.finditer(r'AWO-RETIRE ' + re.escape(nonce) + r' (DONE|BLOCKED)(?![|/])[ \t]*([^\n]*)', text or ''):
        found = (m.group(1), m.group(2).strip())
    return found


# @MX:WARN: sends input to another agent's terminal and may close it.
# @MX:REASON: closing is allowed only after a nonce-bound DONE report AND a git re-check shows no own dirty files.
def retire(row, apply, timeout_ms, send, wait_idle, read, own_dirty, close, nonce):
    out = dict(handle=row['handle'], title=row['title'], state=row['state'], files=[])
    if row['state'] not in LIVE | DEAD:
        return dict(out, result='refused', reason='only agent or idle-shell terminals can be retired')
    before = list(own_dirty(row['handle']))
    out['files'] = before
    if row['state'] in DEAD:
        if before:
            return dict(out, result='kept_needs_human', reason='no live agent to commit its uncommitted files')
        if not apply:
            return dict(out, result='preview', reason='would close: nothing of this terminal is left uncommitted')
        close(row['handle'])
        return dict(out, result='closed', reason='no uncommitted files of this terminal')
    if not apply:
        return dict(out, result='preview', reason='would ask the agent to save and commit its own files, then verify and close')
    if not wait_idle(row['handle'], 3000):
        return dict(out, result='kept_busy', reason='agent is in the middle of a turn; not interrupted')
    token = nonce()
    shown = ', '.join(f.split(':', 1)[-1] for f in before[:30]) or '없음'
    send(row['handle'], RETIRE_PROMPT.format(nonce=token, files=shown))
    if not wait_idle(row['handle'], timeout_ms):
        return dict(out, result='kept_no_report', reason='agent did not finish before the timeout')
    report = parse_retire(read(row['handle']), token)
    if report is None:
        return dict(out, result='kept_no_report', reason='no AWO-RETIRE report line found')
    if report[0] == 'BLOCKED':
        return dict(out, result='kept_blocked', reason=report[1] or 'agent reported BLOCKED')
    after = list(own_dirty(row['handle']))
    if after:
        return dict(out, files=after, result='kept_uncommitted', reason='agent reported DONE but its files are still uncommitted')
    close(row['handle'])
    return dict(out, result='closed', reason=report[1] or 'agent reported DONE and git re-check is clean')


def own_dirty_files(handle):
    import awo_ledger
    from awo_report import dirty_entries
    mine = awo_ledger.files_of(terminal=handle)
    out, cache = [], {}
    for repo, rel in sorted(mine):
        if repo not in cache:
            cache[repo] = [r for _, r in dirty_entries(repo)] if Path(repo).is_dir() else []
        if any(rel == d or (d.endswith('/') and rel.startswith(d)) for d in cache[repo]):
            out.append(f'{repo}:{rel}')
    return out


def wait_idle(handle, ms):
    try:
        value = orca('terminal', 'wait', '--terminal', handle, '--for', 'tui-idle', '--timeout-ms', str(int(ms)))
    except (RuntimeError, ValueError, subprocess.SubprocessError, OSError):
        return False
    wait = value.get('result', {}).get('wait', {}) if isinstance(value.get('result'), dict) else {}
    return bool(wait.get('satisfied'))


def read_screen(handle):
    value = orca('terminal', 'read', '--terminal', handle, '--screen', '--limit', '400')
    term = value.get('result', {}).get('terminal', {})
    tail = term.get('tail') if isinstance(term, dict) else None
    return '\n'.join(tail) if isinstance(tail, list) else str(tail or '')


def orca(*args):
    limit = 40
    if 'wait' in args[:2] and '--timeout-ms' in args:
        limit += int(args[args.index('--timeout-ms') + 1]) / 1000
    p = subprocess.run(['orca', *args, '--json'], capture_output=True, text=True, timeout=limit)
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
    parser.add_argument('--retire', metavar='SELECTOR', help='handle prefix or title part of ONE terminal to wrap up and close')
    parser.add_argument('--timeout-minutes', type=float, default=20, help='with --retire: how long the agent may take')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.threshold_hours) or args.threshold_hours <= 0:
        parser.error('threshold must be positive')
    if args.apply and not (args.close_safe or args.retire):
        parser.error('--apply requires --close-safe or --retire')
    if args.retire and args.close_safe:
        parser.error('use either --retire or --close-safe')
    try:
        paths = project_paths(args.project)
        now = int(time.time() * 1000)
        self_handle = os.environ.get('ORCA_TERMINAL_HANDLE')
        inv = inventory(paths, orca('terminal', 'list'), now, args.threshold_hours, self_handle)
        results = []
        if args.retire:
            if inv['truncated']:
                raise RuntimeError('Terminal listing is truncated; refusing to retire')
            target = select(inv['rows'], args.retire)
            outcome = retire(target, args.apply, int(args.timeout_minutes * 60000),
                             send=lambda h, t: orca('terminal', 'send', '--terminal', h, '--text', t, '--enter'),
                             wait_idle=wait_idle, read=read_screen, own_dirty=own_dirty_files,
                             close=lambda h: orca('terminal', 'close', '--terminal', h),
                             nonce=lambda: secrets.token_hex(4))
            if args.json:
                print(json.dumps(outcome, ensure_ascii=False, indent=2))
            else:
                print(f"{outcome['result']}: {outcome['handle']} {outcome['title'][:50]}")
                print('  ' + outcome['reason'])
                for f in outcome['files']:
                    print('  uncommitted: ' + f)
            return 0 if outcome['result'] in ('closed', 'preview') else 3
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
