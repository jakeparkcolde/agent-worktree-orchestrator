\
# Agent Worktree Orchestrator — Workspace Contract

This repository is a control plane for operating AI coding work across multiple Git repositories.

The user's goal is product work. Git/worktree lifecycle management should be handled by the orchestrator within the safety rules below.

## Source of truth

- Project registry: `projects.yaml`
- Git/Orca operating skill: `skills/git-orchestrator/SKILL.md`
- CLI entry point: `bin/awo`
- Safety model: `docs/safety-model.md`

## Core rules

1. Never develop features directly on a configured base branch.
2. One independent goal should use one short-lived worktree.
3. Reuse an existing worktree when the user's request is a continuation of the same goal.
4. Independent Orca worktrees should use `--no-parent`.
5. `--no-parent` controls Orca lineage; it does not select the Git base.
6. Set/use the configured repo `base_ref` for independent work.
7. Do not create speculative worktrees for future tasks.
8. Respect `max_worktrees`.
9. Before creating a new worktree, inspect existing worktrees for overlap and cleanup candidates.
10. Do not auto-delete dirty, unpushed, unique, or unmerged work.

## Start workflow

Before work:

1. identify target project
2. load `projects.yaml`
3. run `bin/awo status <project>`
4. fetch remote refs
5. inspect merge/rebase/cherry-pick state
6. inspect active worktrees
7. reuse same-goal worktree if present
8. detect overlap on shared files
9. create a new worktree only when needed

## Independent task

Use the equivalent of:

```bash
orca worktree create \
  --repo id:<repo-id> \
  --name <task-name> \
  --no-parent \
  --agent <codex|claude> \
  --prompt "<goal>" \
  --json
```

The repo base ref must already be configured separately.

## High-conflict files

Treat these as coordination hotspots:

- package manager lockfiles
- package manifests
- database schemas
- migrations
- shared layout/design-system files
- shared API types/contracts
- auth configuration
- deployment configuration

Avoid assigning overlapping edits to parallel agents.

## Before merge

1. ensure intended changes are committed
2. fetch the configured base
3. compute ahead/behind
4. update from base when necessary
5. run configured validation
6. inspect diff
7. classify risk
8. follow `merge_policy`

## Risk

Human approval is mandatory for:

- database schema/migrations
- authentication/authorization
- billing/payments
- production infrastructure
- secrets/credentials
- destructive data operations
- permission model changes
- breaking external APIs
- major architecture changes

## Cleanup

Default cleanup is dry-run.

Do not automatically run:

```bash
orca worktree rm --force
git branch -D
git reset --hard
git clean -fd
git push --force
```

Only remove a worktree when it is clean and its HEAD is fully contained in the configured base with no unpushed unique commits.

## Reporting

Prefer a short result:

```text
✓ project / goal complete
✓ validation passed
✓ PR/merge status
✓ cleanup status
active worktrees: N
```

Only surface Git details when they require user action.
