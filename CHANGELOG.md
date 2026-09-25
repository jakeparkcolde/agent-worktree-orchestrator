# Changelog

## Unreleased

- Add a time-limited local Jev trial journal and explicit feedback/report commands;
  separate production from smoke, omit request/candidate text and preserve rule actions
  on recording failures. Configured expiry blocks further provider calls.

- Add opt-in `request --advise jev` project/existing-goal recommendations with
  typed request classification; preserve rule decisions and disable advice on apply.
- Validate bounded Jev responses and verified local task IDs; load credentials
  from the environment or an owner-only `~/.config/awo/jev.env` without shell evaluation.
- Add offline Korean evaluation fixtures and document external data scope,
  manual selection, failure states and rollback.

- Add a work ledger (`awo ledger`): a Claude PostToolUse hook and Codex rollout
  ingestion record which session changed which file in which repository.
- Add `awo report`: cross-project uncommitted files by owner session, runtime
  files, unpushed and far-behind branches, shared-checkout warnings; optional
  09:00 launchd job (`awo launchd install --job report`).
- Add `awo terminals --retire`: ask one idle agent to save and commit only its
  own files, verify with git and the ledger, then close its terminal.
- Add `awo guard`: warn (or block) when editing another project's primary checkout.
- Add `awo hooks install|uninstall|status` with preview and backup.
- Add `awo shared` to list identical and diverged copies of modules across repos.
- Add `awo terminals`: classify a project's Orca terminals, warn when several
  agents work in one checkout, and close only exited, duplicate or idle-prompt
  terminals with `--close-safe --apply` (live agents are never closed).
- Separate coordinator dispatch from independent Orca worker execution.
- Require explicit goal delivery and report creation/session/turn evidence
  separately; preserve worktrees when dispatch is incomplete.
- Document exact-path reuse and prohibit coordinator implementation fallback.
- Add `request` project aliases, goal preview, local associations and worktree reuse.
- Require a concrete goal and inspection of unregistered work before creation.
- Support `start ... none` for the current agent; pass the configured base explicitly.
- Document hub integration without modifying the hub repository.

## 0.2.0 — 2026-09-08

- Add worktree audit evidence and conservative discovery/activity protection.
- Separate commit topology, patch equivalence and final tree differences.
- Preserve runtime/artifacts and require explicit cleanup targeting.
- Add watch thresholds and optional macOS scheduling/notifications.
- Document safety limits and deferred verified archival/semantic analysis.
- Retain v0.1 command forms except unsafe untargeted cleanup application.

## 0.1.0 — 2026-09-07

Initial public template:

- project registry
- Orca independent worktree handoff
- status inspection
- merge-readiness check
- risk classification
- dry-run cleanup
- English/Korean documentation
- contribution and security docs
