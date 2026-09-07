\
# Usage

## Register projects

```bash
cp projects.example.yaml projects.yaml
```

Use absolute paths.

## Inspect

```bash
./bin/awo doctor
./bin/awo status myapp
```

## Start work

```bash
./bin/awo start myapp task-name codex "Goal..."
```

## Continue work

If the same Goal already has a worktree, the AI orchestrator should reuse it rather than call `start` again.

## Finish check

Inside the worktree:

```bash
/path/to/awo/bin/awo finish
```

This checks:

- clean status
- base movement
- unique commits
- upstream/unpushed state
- high-risk filename patterns

## Cleanup

Preview:

```bash
./bin/awo cleanup myapp
```

Apply:

```bash
./bin/awo cleanup myapp --apply
```

## Recommended AI prompt

```text
Use this repository as the control plane.
For all Git and Orca lifecycle actions, follow AGENTS.md and
skills/git-orchestrator/SKILL.md.

Goal:
<your task>
```
