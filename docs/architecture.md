\
# Architecture

## Problem

AI coding agents make parallel implementation cheap, but each parallel task creates operational state:

- branch
- worktree
- agent session
- local dependencies
- PR
- CI status
- merge state

Without a lifecycle policy, these states accumulate.

## AWO model

AWO separates **goal selection** from **execution isolation**.

```text
Goal
 │
 ▼
Project registry
 │
 ▼
Preflight
 │
 ├─ reuse existing worktree?
 ├─ cleanup safe merged work?
 └─ create independent worktree?
 │
 ▼
Orca + coding agent
 │
 ▼
validation
 │
 ▼
risk gate
 │
 ▼
PR / merge
 │
 ▼
safe cleanup
```

## Control plane

The AWO repository is intentionally separate from product repositories.

It contains:

- project registry
- safety policy
- agent instructions
- lifecycle scripts

It should not own product source code.

## Data plane

Each product repo remains a normal Git repository.
Orca creates task worktrees around those repos.

## Lifecycle

```text
NEW
 ↓
ACTIVE
 ↓
IN_REVIEW
 ↓
MERGED
 ↓
CLEANED
```

Exceptional states:

```text
STALE
BLOCKED
UNSAFE_TO_CLEAN
```

## Why short-lived worktrees

The longer independent branches live, the more likely they are to:

- drift from base
- overlap shared files
- cause expensive conflicts
- become hard for humans to reason about

The target is not “few worktrees forever”.
The target is **small worktrees with fast turnover**.
