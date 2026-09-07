\
# Contributing

Thanks for contributing.

## Principles

- preserve user work
- prefer explicit safety checks
- keep scripts auditable
- avoid hidden destructive behavior
- add tests for safety regressions

## Development

```bash
make test
```

If ShellCheck is installed:

```bash
make lint
```

## Pull requests

Keep PRs focused.
Explain any change that affects deletion, branch movement, force-push behavior, or base-ref selection.

## Compatibility

Please include:

- OS
- Git version
- Orca version when relevant
- shell version

in bug reports.
