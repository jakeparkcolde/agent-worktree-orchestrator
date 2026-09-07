#!/usr/bin/env bash
set -euo pipefail

OWNER="${GITHUB_OWNER:-Jakecolde}"
REPO="${GITHUB_REPO:-agent-worktree-orchestrator}"
VISIBILITY="${GITHUB_VISIBILITY:-public}"
DESCRIPTION="Control plane for AI coding agents using Git worktrees, Orca, Codex, and Claude."

command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
command -v gh >/dev/null 2>&1 || {
  echo "GitHub CLI (gh) is required."
  echo "Install: brew install gh"
  echo "Then authenticate: gh auth login"
  exit 1
}

gh auth status >/dev/null

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d .git ]; then
  git init -b main
fi

git add .
if ! git diff --cached --quiet; then
  git commit -m "chore: initial open-source release v0.1.0"
fi

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "Repository already exists: $OWNER/$REPO"
else
  gh repo create "$OWNER/$REPO" \
    "--$VISIBILITY" \
    --description "$DESCRIPTION" \
    --source . \
    --remote origin \
    --push
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "https://github.com/$OWNER/$REPO.git"
fi

git branch -M main
git push -u origin main

# Create v0.1.0 release if it does not already exist.
if ! gh release view v0.1.0 --repo "$OWNER/$REPO" >/dev/null 2>&1; then
  gh release create v0.1.0 \
    --repo "$OWNER/$REPO" \
    --title "v0.1.0 — Initial public release" \
    --notes-file CHANGELOG.md
fi

echo
echo "Published:"
echo "https://github.com/$OWNER/$REPO"
