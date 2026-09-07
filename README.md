<p align="center">
  <img src="docs/assets/awo-mark.svg" width="88" height="88" alt="AWO branching worktree logo">
</p>

# Agent Worktree Orchestrator

**One goal. One worktree. A clearer path from task to cleanup.**

A small CLI and operating contract for managing AI coding work across Git repositories with Orca, Codex, and Claude. Inspect worktrees, start independent tasks from a configured base, and preview cleanup before removing merged work.

[![CI](https://github.com/jakeparkcolde/agent-worktree-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/jakeparkcolde/agent-worktree-orchestrator/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.1.0-blue)](https://github.com/jakeparkcolde/agent-worktree-orchestrator/releases/tag/v0.1.0)
[![Status](https://img.shields.io/badge/status-experimental-orange)](#status)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**English** · [한국어](README.ko.md)

[Quick Start](#quick-start) · [Why](#why) · [Safety](#safety) · [Usage guide](docs/usage.md)

## Why

Parallel coding creates more than code: branches drift, worktrees accumulate, and agents can collide on shared files. AWO gives the human or supervising agent a repeatable workflow and a shared project registry.

- **Keep work tied to a goal.** The operating contract calls for reusing a worktree when continuing the same task.
- **Start independent work deliberately.** The CLI sets the configured base ref, uses Orca `--no-parent`, and checks the worktree limit.
- **Make Git state visible.** Status and finish commands report the state you need to review before merging.
- **Preserve unfinished work.** Cleanup defaults to a preview and checks Git state before removal.

## Use cases

| Situation | How AWO helps |
| --- | --- |
| You work across several repositories | Store paths, base refs, and workflow preferences in `projects.yaml`. |
| You start an independent fix or feature | Create an Orca worktree and launch a Codex or Claude task. |
| You return to an existing goal | Inspect status, then reuse the worktree under the operating contract. |
| You have finished and merged a task | Preview cleanup; apply it only to eligible worktrees. |

## Quick Start

Requires **macOS or Linux, Git, Bash, and Python 3**. Task creation also requires the **Orca CLI** and the **Codex or Claude CLI** you intend to launch. The target repository must already exist locally with an accessible `origin` remote and base ref.

### 1. Clone and configure

```bash
git clone https://github.com/jakeparkcolde/agent-worktree-orchestrator.git
cd agent-worktree-orchestrator
cp projects.example.yaml projects.yaml
```

Edit `projects.yaml` with your editor. Keep the example's simple indentation and replace the project entry with your repository details:

```yaml
projects:
  myapp:
    path: "/absolute/path/to/myapp"
    base_ref: "origin/main"
    max_worktrees: 3
    default_agent: "codex"
    merge_policy: "manual"
    test_command: "npm test"
    lint_command: "npm run lint"
    typecheck_command: "npm run typecheck"
```

Use validation commands appropriate to your project. They are guidance for the supervising agent; `finish` does not run them. `max_worktrees` includes the primary checkout, so `3` allows up to two additional worktrees.

### 2. Check the environment and current work

```bash
./bin/awo doctor
./bin/awo status myapp
```

`doctor` checks tool availability and the configuration file's presence. Review existing work before starting: reuse an existing worktree for the same goal and coordinate overlapping file edits.

### 3. Start an independent task

```bash
./bin/awo start myapp fix-login codex \
  "Fix the intermittent login failure and add regression tests."
```

This fetches `origin`, checks the primary checkout for an in-progress Git operation, verifies the base and worktree count, registers the repository with Orca if needed, and creates the task. `--no-parent` controls Orca lineage; the base ref is configured separately by AWO.

### 4. Validate and review

Run your project's tests, lint, and type checks in the task worktree, review the diff, and commit the intended changes. Then run:

```bash
./bin/awo finish /absolute/path/to/task-worktree
```

`finish` reports ahead/behind counts, changed files, filename-based risk candidates, and upstream status. It compares against `origin/HEAD`, falling back to `origin/main`; it currently does not read the project's `base_ref`. Review against your configured base separately if it differs. Follow your merge policy to open a PR or merge.

### 5. Preview cleanup after merging

```bash
./bin/awo cleanup myapp
```

After reviewing the preview, apply cleanup with:

```bash
./bin/awo cleanup myapp --apply
```

## Architecture

```mermaid
flowchart TD
    H[Human goal] --> O[Human or supervising agent]
    C[AGENTS.md + projects.yaml + operating skill] --> O
    O --> A[AWO CLI: status and start]
    A --> R[Orca: configured base + no-parent]
    R --> W[Task worktree: Codex or Claude]
    W --> V[Run project checks + awo finish]
    V --> M[Human or external workflow: review and merge]
    M --> P[awo cleanup: preview]
    P --> G{Apply requested and Git checks pass?}
    G -->|Yes| D[Remove eligible worktree without force]
    G -->|No| K[Keep worktree]
```

AWO supplies scripts and policy. The human or supervising agent coordinates goals, validation, approval, and merging; Orca runs the worktree task. See [architecture](docs/architecture.md) and [Orca integration](docs/orca-integration.md).

## Safety

> If safety cannot be proven from Git state, preserve the work.

Cleanup is **dry-run by default**. A removable worktree must be outside the primary checkout, clean, have no commits unique to the configured base, and have its HEAD contained in that base. If an upstream exists, it must also have no unpushed commits relative to it. `--apply` uses non-force worktree removal and `git branch -d`; a branch is preserved if deletion fails.

The operating contract prohibits automatically using `orca worktree rm --force`, `git branch -D`, `git reset --hard`, `git clean -fd`, or `git push --force`.

Human approval is required for schema/migrations, authentication/authorization, billing/payments, production infrastructure, secrets, destructive data operations, permissions, breaking external APIs, and major architecture changes. Filename-based risk hints are not a complete risk assessment.

| Merge policy | Responsibility |
| --- | --- |
| `manual` | A human decides whether to merge. Start here. |
| `review` | The supervising workflow follows PR review. |
| `auto` | An external orchestrator may merge low-risk work after validation. |

These policies guide the supervising workflow; the CLI does not enforce approval or merge PRs. Read the [safety model](docs/safety-model.md) and [workspace contract](AGENTS.md).

## Status

**v0.1.0 · Experimental.** Start with `merge_policy: "manual"` on repositories recoverable from remote backups.

Available today: dependency checks, repository/worktree status, Orca task creation, a Git finish report, and cleanup preview/application. Automatic same-goal reuse, overlap detection, configured test execution, PR creation, and merging are not implemented by the CLI. The operating contract assigns those decisions and actions to the human or supervising agent.

See the [roadmap](docs/open-source-roadmap.md) and [changelog](CHANGELOG.md).

## Documentation and contributing

- [Usage guide](docs/usage.md) — command details
- [Operating skill](skills/git-orchestrator/SKILL.md) — guidance for supervising agents
- [Contributing](CONTRIBUTING.md) — small, auditable changes welcome
- [Security policy](SECURITY.md) — reporting security issues

Safety changes should include a regression test when possible.

## License

[MIT](LICENSE)
