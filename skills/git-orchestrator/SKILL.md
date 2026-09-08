---
name: git-orchestrator
description: Manage project selection, Git worktrees, Orca agent handoffs, merge readiness, risk gates, and safe cleanup.
---

# Git Orchestrator

## Objective

Minimize human Git administration while preventing work loss and long-lived branch drift.

Priority:

1. preserve user work
2. minimize base drift
3. keep worktrees short-lived
4. avoid parallel edit overlap
5. automate only when safety is observable

## New worktree decision

Do not create a new worktree for:

- research-only tasks
- code review with no edits
- a continuation of the same existing goal
- an already-active identical task

Create an independent top-level worktree for:

- a new feature
- an independent bug fix
- an independent refactor
- a change intended for its own PR

Only create stacked/child work when the new task genuinely requires an unmerged parent change.

## Preflight

1. resolve project config
2. verify repo path
3. fetch remote refs
4. verify base ref exists
5. detect Git operation in progress
6. inspect dirty state
7. inspect worktree count
8. inspect same-goal worktree
9. inspect likely file overlap
10. preview cleanup if at limit; apply only with explicit authorized selection

## Coordinator and independent worker handoff

Keep the primary checkout as the coordinator's dispatch context. Its role is
project selection, goal assignment, overlap coordination and result collection.
Actual implementation runs in a separate Orca agent terminal bound to the exact
selected worktree. Never `cd` the coordinator into that worktree and implement
as a fallback when independent dispatch is incomplete.

For a new goal use AWO's start flow with an explicit task name, agent and goal.
For the same goal select the registered existing worktree by exact path.
Unknown terminal identity blocks reuse dispatch by default. `--new-session`
requires `--worktree` and explicit knowledge that existing terminals contain no
worker; it never overrides a known agent or incomplete listing. Do not infer
idle-shell status from missing agent metadata. Verify
the binding before reporting the handoff confirmed; do not use an implicit active terminal.
`--no-parent` controls Orca lineage, while the configured base selects the Git
starting point for new worktrees. Reuse must preserve existing worktree state.

Report these facts separately:

1. Worktree created or selected: the exact Git path is known.
2. Session ready: a separate worker terminal exists and is bound to that path.
3. Turn started: execution evidence confirms the worker received the goal and
   began the task. Sending text alone must not be reported as completed work.

On failure, report the last verified stage and preserve the worktree. Repair or
retry dispatch without starting a duplicate worker. Do not claim automatic
background monitoring or natural-language routing unless separately implemented.

## During work

- keep the goal narrow
- commit meaningful checkpoints
- avoid unrelated refactors
- add/update tests
- periodically inspect base movement on long tasks
- update Orca worktree comment/status when useful

## Merge readiness

Fetch base and compare:

```bash
git fetch --prune origin
git rev-list --left-right --count <base>...HEAD
```

If base moved significantly, synchronize and re-run validation.

Prefer rebase for a private feature branch when history rewrite is safe.
If force-pushing after rebase, use `--force-with-lease`, never `--force`.

## Validation

Run project-configured commands when present:

1. targeted tests
2. test suite
3. lint
4. typecheck
5. build if relevant

Never report success for a command that was not run or did not pass.

## Risk gates

LOW:
- docs
- copy
- small UI
- tests
- obvious bug fix
- behavior-preserving refactor

MEDIUM:
- general features
- shared components
- dependencies
- APIs
- multi-module edits

HIGH:
- DB schema/migrations
- auth
- billing/payments
- permissions
- production infra
- secrets
- destructive data changes
- breaking external API
- major architecture change

HIGH requires human approval.

## Cleanup

Follow `docs/safety-model.md`: primary/recent/dirty/unknown worktrees remain
protected. Require HEAD containment, zero unique patches and zero final tree
diff; preserve artifacts, runtime, ignored/untracked and hidden tracked state.
Preview by default. Application needs `--worktree PATH` or explicit `--all-safe`.
Keep branches. Reaching the worktree limit does not authorize deletion.

Never auto-use:

```bash
orca worktree rm --force
git branch -D
git reset --hard
git clean -fd
git push --force
```

If state is ambiguous, preserve the worktree and report why.
