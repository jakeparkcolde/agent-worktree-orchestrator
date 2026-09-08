# Orca integration

AWO uses Orca to dispatch implementation to a separate worker. The primary
checkout remains the coordinator's context for selecting projects, assigning
goals and collecting results; the coordinator must not implement by entering
the worker's directory as a fallback.

## New independent work

Use an explicit goal:

```bash
./bin/awo start myapp fix-login codex \
  "Fix the flaky login test and add regression coverage."
```

The configured `base_ref` selects the starting Git state. Orca `--no-parent`
controls lineage and does not itself select the base. Independent work must not
silently inherit an unrelated feature branch. Use stacked work only when the
new goal actually depends on an unmerged parent.

## Handoff evidence

These stages are different:

| Stage | What it establishes |
| --- | --- |
| Worktree created or selected | The exact target path is known. |
| Session ready | A separate worker terminal is bound to that worktree. |
| Turn started | Execution evidence confirms the worker began the delivered goal. |

A worktree path is not proof of a ready session. A ready terminal is not proof
that a goal was delivered or execution started. Report only verified stages;
never infer completion from creation or from sending a prompt.

## Failure and reuse

Preserve a created worktree if later dispatch fails. Report the failed stage
and any verified target/session identifiers so the handoff can be repaired
without creating duplicate work. Do not fall back to coordinator implementation.

When continuing the same goal, select its registered worktree:

```bash
./bin/awo start myapp fix-login codex "Continue the login regression fix." \
  --worktree /absolute/path/to/task-worktree
```

This preserves its branch and edits. With no terminals, dispatch creates the
selected Codex/Claude worker automatically. Unknown existing terminals block
by default: public metadata cannot establish that they are plain idle shells.
When you know they contain no worker, explicitly acknowledge a new session:

```bash
./bin/awo start myapp fix-login codex "Continue the login regression fix." \
  --worktree /absolute/path/to/task-worktree --new-session
```

The option is valid only with `--worktree`. It does not override a positively
identified agent or a truncated terminal listing. Existing sessions are neither
stopped nor sent prompts. Select by exact path, not an active UI selection.
Coordinate file overlap before dispatching simultaneous goals.

## Dispatch receipt

The `awo_dispatch` JSON field reports what the CLI could verify. A confirmed
session means the returned terminal identity matches the exact worktree and
branch and has a connected agent. It does not certify a started/completed task
turn; observe worker execution separately. A goal omitted from the legacy
command form starts no assigned task.

| Receipt state | Exit | Meaning |
| --- | --- | --- |
| `session_confirmed` | 0 | Independent agent identity confirmed; goal supplied, turn progress unverified. |
| `idle` | 0 | Independent agent confirmed; no goal supplied. |
| `existing_terminal` | 3 | Existing agent or uncertain terminal identity; no new worker or prompt. |
| `unverified` | 3 | Dispatch verification incomplete; inspect before retrying. |

The receipt also includes the agent, reason and, when verified/available, path,
branch and terminal identifier. Earlier preflight/command errors exit 1 and may
not return a receipt. Never assume those errors prove nothing was created.
New-worktree dispatch fetches `origin` and passes the configured base directly
to creation; reuse does not fetch, reset or change the existing branch.

Do not interpret a successful creation response as execution progress.

## Scope

This dispatch flow does not provide automatic natural-language repository
matching, same-goal matching or background task monitoring. The supervising
workflow makes those decisions and observes results explicitly.
