# Working on Birdwatcher

Rules for anyone changing this repository, people and coding agents alike. The README explains what Birdwatcher does and how to use it.

## Layout and layers

```
birdwatcher/
  __init__.py, __main__.py   entry points (`birdwatcher`, `python -m birdwatcher`)
  cli.py                     arguments -> the app, or `check`
  core/                      findings, the check interface, running checks,
                             the course folder, settings
  checks/                    one module per check, and the ALL_CHECKS registry
  ui/                        console output, desktop integrations, the Textual app
    tui/                     app.py (startup, screens), one module per screen,
                             birdwatcher.tcss (all styles)
```

Dependencies point inward: `core <- checks <- ui <- cli`.

- `core` imports nothing else from Birdwatcher and no UI library (no Rich, no Textual).
- `checks` imports `core` and `checks` only.
- `ui` imports anything but `cli`.
- Imports are absolute: `from birdwatcher.core.run import run_checks`.

`birdwatcher/architecture_test.py` enforces these rules. If it fails, move the code to the right layer; never loosen the test to fit.

## Test-first

1. Stub the new function or class with its full docstring (Google style: Args, Returns, Raises).
2. Write contract tests next to the module, named `<module>_test.py`, and see each new test fail for the right reason (not an import error).
3. Implement until the tests pass.

Tests lock in inputs, outputs and side effects, never internals. Anything the user's desktop does (opening VS Code, the folder picker, the network) is passed in as a function, so tests use fakes. App tests drive the real app headless with Textual's pilot. Never weaken or delete a test just to make it pass.

## Common changes

- **A new check:** a module in `checks/` with a `CHECK` id and a function returning a list of `core.findings.Finding`; an entry in `checks.ALL_CHECKS`; a line in the README's checklist.
- **A new screen:** a module in `ui/tui/`; its styles in `birdwatcher.tcss`; the app moves to it from `app.py`.
- **A new setting:** a field on `core.config.Config`, read and written by `load_config` and `save_config`.

## Style

- Ruff, configured in `pyproject.toml`, mirrors the course's style checklist. Run `uv run ruff check` and `uv run ruff format` before committing.
- Course text and error messages go into Rich `Text` objects, never Rich markup, so square brackets show as they are.
- Severity is always shown as a word, never by colour alone.
- Docstrings describe the contract in present tense. Inline comments only explain something surprising.

## Commits

Commit messages describe what changed and why. Commits written with an AI assistant end with its attribution trailer, for example:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
