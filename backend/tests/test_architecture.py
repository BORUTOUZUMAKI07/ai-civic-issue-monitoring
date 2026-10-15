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


# ── mapper-registration guard ────────────────────────────────────────────────
#
# Every ORM model lives in its own domain package and declares string-based
# relationships (``relationship("Issue")``, ``relationship("Ward")``, …). Those
# only resolve once *every* model module has been imported. ``src/models/`` is
# the one module that pulls them all in, and importing any ``src.models.*``
# submodule runs its ``__init__`` too.
#
# Standalone entrypoints (the app factory, the seed scripts, Alembic) are the
# one place no router import chain guarantees this. A regression here is both
# invisible to the unit suite (conftest already registers the mappers) and fatal
# only at runtime — the 2026-10 load-test seed caught exactly that:
# ``InvalidRequestError: expression 'Issue' failed to locate a name``.

# `scripts/evaluate_ml.py` imports the registry at module top; the two seed
# scripts import it inside the function that does the ORM work, so the walk is
# over the whole file rather than just the top level.
_ENTRYPOINTS = (
    SRC / "main.py",
    SRC.parent / "alembic" / "env.py",
    SRC.parent / "scripts" / "seed_wards.py",
    SRC.parent / "scripts" / "evaluate_ml.py",
    SRC.parent / "scripts" / "loadtest" / "seed_user.py",
)


def _imports_registry(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "src.models" or a.name.startswith("src.models.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "src.models" or node.module.startswith("src.models.")):
                return True
    return False


def test_standalone_entrypoints_register_all_models():
    missing = [str(p.relative_to(SRC.parent)) for p in _ENTRYPOINTS if not _imports_registry(p)]
    assert missing == [], (
        "these entrypoints touch the ORM without importing src.models, so string "
        "relationships will fail to resolve at runtime:\n" + "\n".join(missing)
    )
