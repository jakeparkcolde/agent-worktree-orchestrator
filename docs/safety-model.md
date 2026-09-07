\
# Safety model

AWO is designed around one rule:

> If safety cannot be proven from Git state, preserve the work.

## Cleanup invariants

A worktree is removable only when:

1. it is not the primary checkout
2. it has no uncommitted changes
3. it has no commits unique relative to the configured base
4. its HEAD is contained in the configured base
5. if an upstream exists, it has no unpushed commits

`cleanup` defaults to dry-run.

## Prohibited automatic commands

```bash
orca worktree rm --force
git branch -D
git reset --hard
git clean -fd
git push --force
```

## Risk gates

Human approval is required for changes involving:

- schema/migrations
- auth/authorization
- billing/payments
- production infrastructure
- credentials/secrets
- destructive data changes
- permissions
- breaking external APIs
- major architecture changes

## Why not fully autonomous merge?

A passing test suite proves only what the suite covers.
Product intent, migrations, billing behavior, and permission changes can be correct syntactically while still being wrong operationally.

AWO therefore separates:

- mechanical safety
- code validation
- product approval

## Recommended rollout

1. `manual`
2. `review`
3. `auto` only for well-tested LOW-risk repositories
