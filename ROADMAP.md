# AWO v0.2 roadmap

The goal is reliable worktree assessment before cleanup. Two regressions drive
this version: a new zero-commit worktree must remain protected, and commits
with different ancestry must not be mistaken for different content.

## v0.2 scope

- Audit topology-unique commits, `git cherry` equivalent/unique patches, and
  final tree differences independently.
- Track first discovery and observed activity; protect new/recent worktrees.
  Defaults: 24 hours ACTIVE, 72 hours ACTIVE_IDLE for clean worktrees.
- Discover registered Git worktrees, including Orca paths, and record local
  metadata without copying source, runtime logs, or artifact contents.
- Distinguish ACTIVE, ACTIVE_IDLE, MERGE, SYNCED, STALE, ARCHIVE,
  SAFE_CLEANUP, BLOCKED, and REVIEW. Explain blocked cleanup decisions.
- Distinguish runtime, artifacts, scratch, and ordinary code; keep tracked,
  untracked, and ignored state visible to safety checks.
- Require explicit `--worktree` or `--all-safe` for cleanup application;
  preserve branches and use non-force removal.
- Watch at 24/72/168 hours, warn at the configured worktree limit, support
  optional macOS notifications and launchd setup/removal.
- Preserve the existing doctor/status/start/finish command forms.

## Safety acceptance criteria

Cleanup must refuse primary, dirty, conflicted, recently created/active,
protected, or incompletely inspected worktrees. Patch equivalence alone is
insufficient: a nonzero final tree diff prevents automatic cleanup. Unpushed
work and artifacts must remain protected. Tracked runtime must never be
silently restored or deleted. No process is automatically terminated.

Unknown creation time uses first observation conservatively, even for an old
checkout. Ordinary observation must not reset activity on every invocation.

## Deferred work

- Verified archive command: preview, explicit application, file counts and
  checksum verification, and durable archive receipts. Until available,
  artifact presence blocks cleanup; a manually copied archive is not proof.
- SEMANTICALLY_SYNCED certification. A tiny diff or many equivalent patches
  cannot establish semantic equality. Nonzero differences require review.
- Base-quality labels GOOD BASE / STALE BASE and reliable STACKED origin
  detection: Git ancestry alone does not prove which
  branch the user selected when creating a worktree.
- Automatic goal reuse, overlapping-edit coordination, configured validation
  execution, PR creation and merging remain supervising-workflow duties.

Optional agent session inspection should show process identity, TTY and age
without command arguments; recommend closing completed sessions in Orca.
No automatic kill or session-age-based deletion is acceptable.

## Configuration and compatibility

The example registry documents supported v0.2 settings. Keep v0.1 project
entries valid by supplying defaults for new fields. The deliberate safety
change is that bare `cleanup PROJECT --apply` no longer removes all candidates.

## Release gate

Run regression tests and `git diff --check`, review the staged paths for
private state/logs/artifacts, and publish source only. Tag a release only when
existing repository release practice and verification support it.

## Planned natural-language entry flow

A supervising Codex workflow could accept “AWO 카카오 비서관련 레포 작업 하고
싶다”, resolve the repository from registered project names/aliases, and inspect
existing worktrees before deciding what to start. This natural-language routing
and alias support are planned; the current CLI does not implement them.

1. Resolve the intended registered repository. Ask only when the match is
   ambiguous or the task goal is missing.
2. Inspect existing worktrees and reuse one for the same goal.
3. For a concrete independent goal, choose a task name and call the existing
   `awo start PROJECT TASK_NAME AGENT GOAL` command.
4. Use the configured `base_ref` (normally `origin/main`) with Orca
   `--no-parent`; do not assume every project uses main.
5. Confirm the created path/base and report where work will continue.

Do not create speculative worktrees merely because a repository was mentioned.
The CLI still requires a task name and goal supplied by the supervising workflow.
