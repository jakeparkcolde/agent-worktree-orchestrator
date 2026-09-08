# Usage

## Configuration

Copy `projects.example.yaml` to `projects.yaml` and use absolute repository
paths. `AWO_PROJECTS_FILE` selects a different registry. Existing flat v0.1
entries remain valid. Optional flat fields are `active_hours: 24`,
`recent_hours: 72`, and `stale_hours: 168`; protection cannot be reduced below
24/72 hours. `max_worktrees` includes the primary checkout.

## Inspect and start

```bash
./bin/awo doctor
./bin/awo status myapp
./bin/awo audit myapp
./bin/awo audit myapp --json
./bin/awo start myapp task-name codex "Goal..."
```

Audit reports topology, patch and final-tree evidence separately. Discovery
records local metadata in the Git common directory, including worktrees created
outside AWO. Audit/watch use existing local refs and do not fetch; cleanup
application fetches `origin` before assessing removal. Unknown age starts at first observation. Old commits do not bypass
new-worktree protection. Orca detection is a path-based inference.

Reuse an existing worktree when continuing the same goal. `start` still uses
the existing Orca integration; AWO does not automatically detect matching goals.

## Finish

```bash
./bin/awo finish /absolute/path/to/task-worktree
```

The existing finish report checks Git status, base movement, unique commits,
upstream state and filename risk hints. Run project validation yourself. Finish
uses `origin/HEAD`, falling back to `origin/main`; use audit for the configured
project base. Neither command creates or merges a PR.

## Cleanup

Preview all worktrees or select one:

```bash
./bin/awo cleanup myapp
./bin/awo cleanup myapp --worktree /absolute/path/to/task-worktree
```

Apply to an explicitly selected worktree, or explicitly opt into all safe ones:

```bash
./bin/awo cleanup myapp --worktree /absolute/path/to/task-worktree --apply
./bin/awo cleanup myapp --all-safe --apply
```

Bare `cleanup myapp --apply` is refused. Selection is not a safety override.
Recently discovered or active worktrees remain protected, branches are retained,
and any nonzero final diff blocks removal. Tracked runtime/artifact/scratch detection uses filename/path heuristics;
all ignored/untracked files block removal regardless of their category. Review the reported
reasons; there is no force-cleanup or verified archive command.

## Watch

```bash
./bin/awo watch myapp
./bin/awo watch myapp --json
./bin/awo watch myapp --notify
```

Watch performs one scan. Default thresholds are 24 hours for notice, 72 for
stale and 168 for action required; reaching `max_worktrees` also alerts.
Notifications are optional and macOS-specific. See the launchd helper for
periodic execution. AWO does not clean up worktrees automatically during watch.

## Agent sessions

```bash
./bin/awo sessions --json
./bin/awo watch myapp --sessions --json
```

Session inspection is host-wide and read-only. It does not establish which
project/worktree a process uses; correlate sessions manually. Command arguments
are not collected. Age is not proof of inactivity, and no process is killed.

## macOS scheduling

Both helpers preview by default. Install a 09:00/18:00 job only when desired:

```bash
./bin/awo launchd install myapp --notify
./bin/awo launchd install myapp --notify --apply
./bin/awo launchd uninstall myapp --notify --apply
```

Use the same project and options when uninstalling. Optional `--config` selects
an absolute registry path, `--awo` selects the executable, and `--label` gives
multiple jobs distinct labels. Existing job files are not overwritten.
Application is macOS-only; live desktop integration needs platform validation.

## Limits

Semantic equivalence, verified artifact archival, GOOD BASE / STALE BASE labels
and reliable stacked-branch origin inference are deferred. A tiny final diff always needs review. Read the
[safety model](safety-model.md) and [roadmap](../ROADMAP.md) before applying
cleanup.
