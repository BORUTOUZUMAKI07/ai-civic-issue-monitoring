"""Architecture tests — enforce layering boundaries (DDD).

These are deliberately dependency-free: a pure ``ast`` walk over the source
tree, so no extra package is needed and it runs inside the normal test suite.

Layering (outer layers may import inner ones, never the reverse)::

    shared  <-  core  <-  domains/*  <-  main.py

The rules enforced here are the ones that already hold and must never
regress. They are intentionally conservative; as domains grow their own
``repositories/ports.py`` the matrix will be tightened here.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _imported_src_modules(path: Path) -> set[str]:
    """Return the set of ``src.*`` modules imported by a file (any form)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("src."):
                found.add(node.module)
    return found


def _violations(root: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    problems: list[str] = []
    for path in _iter_python_files(root):
        for module in _imported_src_modules(path):
            if module.startswith(forbidden_prefixes):
                rel = path.relative_to(SRC)
                problems.append(f"{rel} imports {module}")
    return problems


def test_shared_is_a_leaf():
    """The shared kernel must not depend on core, domains, or platform code."""
    violations = _violations(
        SRC / "shared",
        ("src.core", "src.domains", "src.agents", "src.ml", "src.rag"),
    )
    assert violations == [], "shared/ violates layering:\n" + "\n".join(violations)


def test_core_does_not_import_domains():
    """Cross-cutting infrastructure must not depend on any domain."""
    violations = _violations(
        SRC / "core",
        ("src.domains", "src.agents", "src.rag"),
    )
    assert violations == [], "core/ violates layering:\n" + "\n".join(violations)


def test_main_has_no_src_reexports():
    """``main.py`` is composition root only — no stray cycles check for now."""
    # Placeholder: main.py legitimately imports everything; kept explicit so
    # the intent is documented and future rules have a home.
    assert (SRC / "main.py").exists()
