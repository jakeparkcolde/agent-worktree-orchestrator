\
# Security Policy

AWO executes local Git and optional Orca commands in repositories configured by the user.

## Reporting

Please report security-sensitive issues privately to the repository maintainer rather than opening a public issue.

## Threat model

Particular attention should be paid to:

- command injection through configuration values
- unsafe repository paths
- destructive Git commands
- deletion of unique/unpushed work
- credential leakage in logs
- untrusted task prompts causing out-of-scope operations

Do not include secrets in `projects.yaml`, prompts, issue templates, or logs.
