\
# Orca integration

AWO uses Orca as a worktree-native execution layer.

## Base ref

Configure the repo base ref before creating independent worktrees:

```bash
orca repo set-base-ref --repo id:<repo-id> --ref origin/main --json
```

## Independent work

```bash
orca worktree create \
  --repo id:<repo-id> \
  --name fix-login \
  --no-parent \
  --agent codex \
  --prompt "Fix the flaky login test and add regression coverage." \
  --json
```

`--no-parent` means the worktree is independent in Orca lineage.
It does not choose the Git base.

## Stacked work

Only use explicit parent relationships when the child task genuinely depends on an unmerged parent.

## Status notes

Orca can store worktree comments/status, which an orchestrator can use for coordination.

Example:

```bash
orca worktree set \
  --worktree active \
  --comment "implementation complete; running tests" \
  --json
```

## References

- https://www.onorca.dev/docs/cli/reference
- https://www.onorca.dev/docs/model/worktrees
- https://github.com/stablyai/orca/blob/main/skill-guides/orca-cli.md
