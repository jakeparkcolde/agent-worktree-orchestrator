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
- Semantic goal matching, overlapping-edit coordination, configured validation
  execution, PR creation and merging remain supervising-workflow duties.
  Explicit goal association and reuse are implemented by `awo request`.

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

## Natural-language entry flow — implemented on this branch

`awo request TEXT` resolves registered names and pipe-separated aliases, returns
existing worktrees and recorded goals, and asks for a concrete `--goal` before
starting anything. The supervising agent interprets the user's intent; the CLI
does not invoke an LLM. Ambiguous matches require explicit project selection.

With `--apply`, reuse a verified worktree for the same normalized goal or call
`awo start` with the configured base ref and Orca `--no-parent`. Existing worktrees
without goal records must be inspected before association or independent creation.
The default `--agent none` supports continuing in the current agent session.

Do not create speculative worktrees merely because a repository was mentioned.
The CLI still requires a task name and goal supplied by the supervising workflow.

## Coordinator and worker dispatch contract

The primary checkout remains available to the coordinator for parallel task
allocation. Implementation runs in a separate Orca terminal bound to the exact
worktree, with an explicitly delivered goal. Creation, session readiness and
turn start are distinct facts; a created directory is not a running worker.

If worker dispatch fails, preserve the worktree and repair the handoff. Do not
move the coordinator into the worktree and silently perform implementation.
Existing-goal reuse must preserve its checkout and use exact-path selection.
Natural-language project matching is provided separately by `awo request`;
the dispatch contract adds no automatic goal inference or background monitoring.

Metadata is local to the target Git common directory. Reuse preserves dirty work;
missing/replaced worktrees and in-progress Git operations are not silently accepted.
A repository lock serializes request application. See [entry documentation](docs/request-entry.md)
for the supervising workflow, limitations and a proposed hub instruction snippet.
Hub repository files are never installed or modified automatically.
