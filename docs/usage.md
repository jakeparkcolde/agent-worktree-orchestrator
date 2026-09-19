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

## Independent worker dispatch and reuse

Keep the coordinator in its primary checkout context. Implementation must run
in a separate Orca worker terminal for the selected worktree; creating a folder
does not by itself start a task. Supply a concrete goal as shown above.

To select an existing same-goal worktree:

```bash
./bin/awo start myapp fix-login codex "Continue the login regression fix." \
  --worktree /absolute/path/to/task-worktree
```

Reuse preserves the branch and edits. With no terminals, AWO creates the
selected Codex/Claude worker. Public terminal metadata cannot prove that an
unknown terminal is an idle shell, so existing unknown terminals block dispatch
by default. If you know no worker is running there, explicitly acknowledge that
with `--new-session`:

```bash
./bin/awo start myapp fix-login codex "Continue the login regression fix." \
  --worktree /absolute/path/to/task-worktree --new-session
```

`--new-session` requires `--worktree`; it permits an additional terminal only
when no agent is positively identified. A detected agent or a truncated terminal
listing still blocks dispatch. Existing sessions receive no prompt and are not
stopped or changed. Do not use this acknowledgment without knowing their role.

The JSON `awo_dispatch` receipt distinguishes verified session identity from
execution progress. `session_confirmed` and `idle` exit 0; `unverified` and
`existing_terminal` exit 3.
A ready session does not establish that a task turn has started. If verification is incomplete, preserve the worktree and inspect Orca
before retrying. Never move the coordinator into that directory and implement
as an automatic fallback. AWO does not monitor progress in the background.

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

## Orca terminals

Terminals pile up when finished agents leave their shells behind or a
conversation is reopened in a new tab. Inspect one project's terminals:

```bash
./bin/awo terminals myapp
./bin/awo terminals myapp --close-safe          # preview what would close
./bin/awo terminals myapp --close-safe --apply  # close them
```

Each terminal in the project's checkouts is classified:

| State | Meaning | Closed by `--close-safe --apply` |
|---|---|---|
| `SELF` | the terminal running the command | never |
| `WORKING` | agent with recent output | never |
| `IDLE_AGENT` | live agent quiet past the threshold | never (reported only) |
| `EXITED` | agent exited; screen ends at a shell prompt after its resume hint | yes, when idle past the threshold |
| `DUPLICATE` | agent blocked because the conversation is open elsewhere | yes, when idle past the threshold |
| `IDLE_SHELL` | plain shell waiting at a prompt | yes, when idle past the threshold |
| `BUSY_SHELL` | plain shell not at a prompt (it may run a service) | never |
| `UNKNOWN` | Orca reported no activity time | never |

The threshold defaults to 12 hours (`--threshold-hours`). Before closing, each
candidate is re-read and skipped if its state changed. A truncated listing
refuses `--apply`. Closing a terminal does not delete the agent's conversation
history; it can be resumed later.

When two or more agents are working in the same checkout, the command prints a
warning: their uncommitted changes can end up mixed in one commit. Move one of
them to its own worktree (`awo start`).

## Work ledger and ownership

Uncommitted changes pile up when agents edit several repositories and nobody
remembers which session changed what. AWO keeps a work ledger:

```bash
./bin/awo hooks install            # preview the Claude Code hooks
./bin/awo hooks install --apply    # add them to ~/.claude/settings.json (backup first)
./bin/awo ledger who path/to/file  # which session touched this file
./bin/awo ledger files --terminal term_xxx
```

- `PostToolUse` runs `awo ledger record`: every Edit/Write/MultiEdit/NotebookEdit
  appends session, Orca terminal, repository and file to `~/.awo/ledger/*.jsonl`.
- Codex sessions are read from their rollout files (`awo ledger ingest-codex`,
  also run by `awo report`).
- `PreToolUse` runs `awo guard`: editing a file inside ANOTHER registered
  project's primary checkout shows a warning once per session and repository.
  `AWO_GUARD=block` denies instead; `AWO_GUARD=off` disables it.
- Both hooks are fail-open: an error never blocks the agent. Files changed by
  shell commands are not recorded and appear as unknown owner.

## Daily report

```bash
./bin/awo report                   # all registered projects
./bin/awo report --save --notify   # write ~/.awo/reports/YYYY-MM-DD.md
./bin/awo launchd install --job report --notify          # preview 09:00 job
./bin/awo launchd install --job report --notify --apply
```

For every checkout: uncommitted files grouped by owner session (and whether its
terminal is still open), unknown-owner files, tool-written runtime files
(ignore-list candidates), unpushed commits, branches more than 20 commits
behind base, and a warning when several agents work in one checkout.

## Retiring one terminal

```bash
./bin/awo terminals myapp --retire "part of title"          # preview
./bin/awo terminals myapp --retire term_1a2b --apply
```

The selector must match exactly one terminal. For a live agent that is idle at
its prompt, AWO sends one wrap-up request: save unsaved decisions, commit only
the files this session changed (explicit paths, never `git add -A`), no push.
The agent must answer with a line bound to a one-time token
(`AWO-RETIRE <token> DONE|BLOCKED`). AWO then re-checks git using the ledger
and closes the terminal only when nothing of that terminal is left
uncommitted. A busy agent, a BLOCKED answer, a missing answer or leftover files
keep the terminal open with the reason. Terminals without a live agent close
only when the ledger shows no uncommitted files of theirs.

## Shared modules

```bash
./bin/awo shared
./bin/awo shared --repo gitbap=~/gitbap --repo sns=~/repos/sns-marketer
```

Lists files with identical content in several projects, and files with the
same parent folder and name (e.g. `supabase/server.ts`) whose content has
diverged. Tool-managed folders (`.claude`, `.moai`, `node_modules`, ...) are
skipped. Use it to pick one home repository for a module before copies drift
further.

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
