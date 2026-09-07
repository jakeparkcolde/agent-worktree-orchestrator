# Publishing to GitHub

The ChatGPT GitHub connector can edit existing repositories but may not expose repository creation.

This repository includes a one-command local publisher using GitHub CLI.

## Publish

```bash
./scripts/publish-github.sh
```

Default target:

```text
Jakecolde/agent-worktree-orchestrator
```

The script:

1. checks `gh` authentication
2. initializes Git if needed
3. creates the initial commit
4. creates the public GitHub repository when absent
5. pushes `main`
6. creates GitHub Release `v0.1.0`

## Override target

```bash
GITHUB_OWNER=yourname \
GITHUB_REPO=your-repo \
./scripts/publish-github.sh
```

## Prerequisites

```bash
brew install gh
gh auth login
```
