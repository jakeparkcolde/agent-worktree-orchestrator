# Safety model

If safety cannot be proven, preserve the work.

## Separate evidence from permission

Topology-unique commits describe ancestry. `git cherry` describes patch
identity and does not fully account for merge resolution. A final tree diff
compares the configured base with the worktree HEAD; it can include changes
added only on the base. None of these measures alone authorizes removal.
A small nonzero diff is not proof of semantic equivalence.

Cleanup is a preview by default. Applying cleanup requires a selected
`--worktree` or explicit `--all-safe`, and every selected worktree is still
subject to safety checks. Branch history is retained.

## Cleanup gates

- Preserve the primary checkout and protected or recently active worktrees.
- Preserve dirty, conflicted, unpushed, locked, or uninspectable worktrees.
- Require HEAD containment in the configured base, zero unique patches and
  zero final tree differences.
- Preserve artifacts, including ignored artifacts, and tracked runtime files.
- Preserve any worktree whose safety cannot be determined.
- Use non-force Git worktree removal; never delete a branch as a side effect.

Even a merged branch may be refused because the base has moved and its final
tree now differs. This conservative behavior is intentional.

## Time and metadata

A commit date is not a worktree creation date. A newly discovered checkout is
protected from its first observation. Persisted observation metadata provides
continuity, but is not a tamper-proof audit trail. Losing metadata restarts
protection. Default creation/idle protection is 24/72 hours; activity is
tracked separately from merely being seen. State is stored under the Git
common directory at `awo/worktrees.json`; it is not placed in the tracked
working tree. `created_at` remains unknown for discovered worktrees; Unix
`first_seen_at`, `last_seen_at`, and `last_activity_at` track observation.
An Orca source label is inferred from the path, not confirmed by Orca metadata.

## Files and sessions

File classification uses path/extension heuristics; it cannot recognize every
artifact by meaning. All ignored/untracked files block cleanup regardless of
category. Runtime, artifacts, scratch and code are different categories, not exemptions
from preservation. Tracked runtime and scratch are never automatically restored or deleted.
Artifacts are never automatically removed. Archive verification is deferred;
manually archiving a directory does not grant cleanup permission.

Session inspection is advisory only. Process age does not prove inactivity,
and AWO never kills a process. Do not publish runtime logs or process command
arguments containing prompts, tokens or credentials.

## Prohibited automatic operations

No force worktree removal, forced branch deletion, hard reset, recursive clean,
force push, artifact deletion or session termination. AWO does not enforce
product review, execute configured validation, or merge PRs; those remain the
human or supervising workflow's responsibility.
