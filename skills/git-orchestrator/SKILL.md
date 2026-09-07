\
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
10. cleanup safe merged work if at limit

## Orca handoff

For independent work, prefer:

```bash
orca worktree create \
  --repo id:<repo-id> \
  --name <task> \
  --no-parent \
  --agent <agent> \
  --prompt "<goal>" \
  --json
```

`--no-parent` is lineage only. Do not derive an independent task from the current feature branch.

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

A candidate is safe only when:

- worktree is clean
- HEAD is contained in configured base
- no unique commits remain relative to base
- no unpushed commits remain when upstream exists

Default to dry-run.

Never auto-use:

```bash
orca worktree rm --force
git branch -D
git reset --hard
git clean -fd
git push --force
```

If state is ambiguous, preserve the worktree and report why.
