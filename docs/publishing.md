# Publishing to GitHub

The existing upstream is `jakeparkcolde/agent-worktree-orchestrator`.
For an update, review the existing remote and publish only intended source
changes after tests and `git diff --check` pass.

The original `scripts/publish-github.sh` is a bootstrap helper for initial
repository publication. Inspect its defaults before use; it is not the v0.2
release workflow. Do not run it blindly against an existing repository.

A version bump does not create a release. Review existing release practice and
platform verification before tagging v0.2.0. In particular, launchd and desktop
notification integration need validation on macOS; parsing tests alone do not
prove operating-system integration. If verification is incomplete, push the
source commit and document the remaining work without creating a release.

Never include project registry paths, local observation state, archived
artifacts, runtime logs, credentials or process command arguments in commits
or release assets. Review staged paths and use an explicit source-file list.
