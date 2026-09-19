#!/usr/bin/env python3
"""Cross-project edit guard (Claude PreToolUse hook).

Warns when a session edits a file inside ANOTHER registered project's primary
checkout, where the change would pile up as that project's ownerless
uncommitted work. Worktrees and the session's own repository are silent.
AWO_GUARD=warn (default) | block | off. Fail-open: errors never block edits.
"""
import json
import os
from pathlib import Path
import sys

import awo_ledger as ledger
from awo_report import project_list

MESSAGE = ('AWO: {path} 는 다른 프로젝트 「{name}」의 main 체크아웃이에요. 여기서 바로 고치면 {name}의 '
           '주인 없는 미커밋으로 쌓여요. 「AWO {name} <할 일>」처럼 요청하면(`awo request`) 워크트리를 만들어 '
           '거기서 고치고 커밋해요.')


def primaries():
    out = {}
    for name, path, _ in project_list():
        try:
            out[str(Path(path).expanduser().resolve())] = name
        except OSError:
            continue
    return out


def seen_before(session, repo):
    state = ledger.ledger_dir() / 'guard-seen.json'
    try:
        data = json.loads(state.read_text())
    except (OSError, ValueError):
        data = {}
    key = f'{session}|{repo}'
    if key in data:
        return True
    data[key] = 1
    if len(data) > 5000:
        data = dict(list(data.items())[-2500:])
    state.parent.mkdir(parents=True, exist_ok=True)
    tmp = state.with_suffix('.tmp')
    tmp.write_text(json.dumps(data))
    os.replace(tmp, state)
    return False


def check_hook(stream, out):
    try:
        mode = os.environ.get('AWO_GUARD', 'warn')
        if mode == 'off':
            return 0
        payload = json.loads(stream.read())
        if payload.get('tool_name') not in ledger.EDIT_TOOLS:
            return 0
        ti = payload.get('tool_input') or {}
        path = ti.get('file_path') or ti.get('notebook_path')
        if not path:
            return 0
        target = ledger.repo_of(path)
        own = ledger.repo_of(payload.get('cwd') or '.')
        name = primaries().get(target) if target else None
        if not name or target == own:
            return 0
        text = MESSAGE.format(path=path, name=name)
        if mode == 'block':
            out.write(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                                         'permissionDecisionReason': text}}, ensure_ascii=False))
            return 0
        if seen_before(payload.get('session_id'), target):
            return 0
        out.write(json.dumps({'systemMessage': text,
                              'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext': text}}, ensure_ascii=False))
    except Exception:  # fail-open by contract
        pass
    return 0


if __name__ == '__main__':
    sys.exit(check_hook(sys.stdin, sys.stdout))
