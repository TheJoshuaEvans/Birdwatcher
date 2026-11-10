"""
Contract tests for the package's layers. Dependencies point inward:

    core  <-  checks  <-  ui  <-  cli

- core: findings, the check interface, running checks, the course folder,
  settings. Imports nothing else from Birdwatcher and no UI library.
- checks: one module per check, plus the registry. Imports core and checks.
- ui: the console output and the Textual app. Imports anything but cli.
- cli and the package's entry points sit on top and may import anything.

Imports are read with ast, so nothing is imported or run. Test files follow
the same rules as the modules they sit next to.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parent
UI_LIBRARIES = ("rich", "textual")
FORBIDDEN = {
    "core": ("birdwatcher.checks", "birdwatcher.ui", "birdwatcher.cli", *UI_LIBRARIES),
    "checks": ("birdwatcher.ui", "birdwatcher.cli", *UI_LIBRARIES),
    "ui": ("birdwatcher.cli",),
}


def modules_in(layer):
    folder = PACKAGE / layer
    return sorted(folder.rglob("*.py")) if folder.is_dir() else []


def imports_of(path):
    """Every module name a file imports, and whether it uses relative imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names, relative = [], False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = True
            elif node.module:
                names.append(node.module)
    return names, relative


def is_within(name, prefix):
    return name == prefix or name.startswith(prefix + ".")


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_every_layer_has_modules(layer):
    assert modules_in(layer), f"birdwatcher/{layer}/ has no modules"


@pytest.mark.parametrize(
    ("layer", "path"),
    [(layer, path) for layer in sorted(FORBIDDEN) for path in modules_in(layer)],
    ids=lambda value: (
        value.relative_to(PACKAGE).as_posix() if isinstance(value, Path) else value
    ),
)
def test_layer_imports_point_inward(layer, path):
    names, _ = imports_of(path)
    broken = [
        name
        for name in names
        if any(is_within(name, prefix) for prefix in FORBIDDEN[layer])
    ]
    assert broken == [], f"{layer} must not import {broken}"


@pytest.mark.parametrize(
    "path",
    sorted(PACKAGE.rglob("*.py")),
    ids=lambda path: path.relative_to(PACKAGE).as_posix(),
)
def test_imports_are_absolute(path):
    _, relative = imports_of(path)
    assert not relative, "use `from birdwatcher.<layer>.<module> import ...`"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
