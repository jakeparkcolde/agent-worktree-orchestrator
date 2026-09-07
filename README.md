\
# Agent Worktree Orchestrator

> Experimental control plane for AI coding agents using Git worktrees, Orca, Codex, and Claude.

Agent Worktree Orchestrator (AWO) is a small, opinionated toolkit for people who run multiple AI coding agents across multiple repositories and do not want branch/worktree cleanup to become a second job.

Instead of treating every prompt as a new branch, AWO treats a worktree as a **short-lived execution environment for one goal**.

## Why

Parallel AI coding is easy to start and surprisingly hard to operate.

Typical failure modes:

- too many long-lived worktrees
- feature branches drifting far behind `main`
- agents editing the same shared files in parallel
- merged worktrees never being removed
- unpushed commits being deleted accidentally
- humans spending more time managing Git than giving product direction

AWO adds a lightweight orchestration layer:

```text
Human
  │
  │ Goal
  ▼
Orchestrator repo
  │
  ├─ AGENTS.md
  ├─ projects.yaml
  ├─ Git safety policy
  └─ git-orchestrator skill
  │
  ▼
Orca
  │
  ├─ isolated worktree
  ├─ Codex / Claude
  ├─ tests / review
  └─ PR
  │
  ▼
merge → safe cleanup
```

## Core ideas

1. **One worktree = one goal**
2. **Independent work starts from the repo base ref**
3. **Use top-level Orca worktrees for independent tasks**
4. **Prefer reusing an existing worktree over creating another**
5. **Keep active worktrees small in number and short in lifetime**
6. **Never auto-delete dirty or uniquely committed work**
7. **Risky changes require human approval**
8. **`AGENTS.md` describes the workspace contract; the task prompt describes the goal**

## Status

`v0.1.0` — experimental.

Use it on repositories you can restore from remote backups. Start with `merge_policy: manual`.

## Requirements

- macOS or Linux
- Git
- Bash
- Python 3
- Orca CLI for Orca task creation
- Codex and/or Claude CLI if you want Orca to launch those agents

## Quick start

```bash
git clone https://github.com/Jakecolde/agent-worktree-orchestrator.git
cd agent-worktree-orchestrator

cp projects.example.yaml projects.yaml
$EDITOR projects.yaml

chmod +x bin/awo scripts/*.sh
./bin/awo doctor
```

Example project:

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

Check status:

```bash
./bin/awo status myapp
```

Start an independent task:

```bash
./bin/awo start myapp fix-login codex \
  "Fix the intermittent login failure and add regression tests."
```

Check a worktree before PR/merge:

```bash
/path/to/agent-worktree-orchestrator/bin/awo finish
```

Preview cleanup:

```bash
./bin/awo cleanup myapp
```

Apply only safe cleanup candidates:

```bash
./bin/awo cleanup myapp --apply
```

## Safety model

Cleanup is **dry-run by default**.

AWO does not automatically run these destructive commands:

```bash
orca worktree rm --force
git branch -D
git reset --hard
git clean -fd
git push --force
```

A cleanup candidate must be:

- clean
- free of unpushed commits
- free of commits unique relative to the configured base
- fully contained in the configured base

Even with `--apply`, Git's non-force safety checks remain in place.

See [`docs/safety-model.md`](docs/safety-model.md).

## Merge policies

| Policy | Meaning |
| --- | --- |
| `manual` | Prepare and validate; human decides merge |
| `review` | PR/review workflow expected |
| `auto` | Low-risk changes may be auto-merged by an external orchestrator after tests/CI |

AWO itself does **not** blindly merge pull requests. It provides the policy and preflight layer for an AI orchestrator.

High-risk changes always require explicit approval:

- database schema / migrations
- authentication / authorization
- billing / payments
- production infrastructure
- secrets / credentials
- destructive data operations
- permission model changes
- breaking external API changes

## Project structure

```text
.
├── AGENTS.md
├── README.md
├── README.ko.md
├── projects.example.yaml
├── bin/
│   └── awo
├── scripts/
│   ├── common.sh
│   ├── doctor.sh
│   ├── project-value.sh
│   ├── repo-status.sh
│   ├── task-start.sh
│   ├── task-finish.sh
│   └── cleanup.sh
├── skills/
│   └── git-orchestrator/
│       └── SKILL.md
├── docs/
├── examples/
└── .github/
```

## Orca model

Orca is worktree-native: each task can have its own Git worktree, branch, terminals, and agent session. For independent work, Orca documents `--no-parent`; it controls Orca lineage, not the Git base. Set the repository base ref separately and keep independent tasks based on it.

References:

- Orca CLI reference: https://www.onorca.dev/docs/cli/reference
- Orca worktree model: https://www.onorca.dev/docs/model/worktrees
- Orca CLI skill guide: https://github.com/stablyai/orca/blob/main/skill-guides/orca-cli.md
- OpenAI Codex repository: https://github.com/openai/codex
- OpenAI Codex workflow cookbook: https://github.com/openai/openai-cookbook/blob/main/examples/codex/iterating-development-workflows-with-codex.md

## Codex and `AGENTS.md`

Codex recognizes `AGENTS.md` as repository guidance and applies more specific nested instructions as it works deeper in a repository. AWO uses the root `AGENTS.md` as an operating contract and keeps task-specific intent in the goal/prompt.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

Small, auditable changes are preferred. Safety changes should include a regression test when possible.

## License

MIT
