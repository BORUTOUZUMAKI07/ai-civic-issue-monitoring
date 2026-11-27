"""Architecture tests — enforce layering boundaries (DDD).

These are deliberately dependency-free: a pure ``ast`` walk over the source
tree, so no extra package is needed and it runs inside the normal test suite.

Layering (outer layers may import inner ones, never the reverse)::

    shared  <-  core  <-  domains/*  <-  main.py

The rules enforced here are the ones that already hold and must never
regress. They are intentionally conservative; as domains grow their own
``repositories/ports.py`` the matrix will be tightened here. ``main.py`` is
also checked as the composition root: it may import domain *API routers* and
explicit startup checks, but no domain services/repositories, and every router
it imports must actually be registered.
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


MAIN = SRC / "main.py"

# Startup preflights are the one deliberate exception to the router-only rule:
# they run once in the lifespan and must not be hidden behind an HTTP endpoint.
_STARTUP_DOMAIN_IMPORTS = frozenset({"src.domains.users.super_admin"})


def _router_import_aliases(path: Path) -> set[str]:
    """Local names bound by ``from ...domains.X.api.routes import router as ...``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if not (module.startswith("src.domains.") and module.endswith(".api.routes")):
            continue
        for alias in node.names:
            if alias.name == "router":
                aliases.add(alias.asname or alias.name)
    return aliases


def _registered_router_names(path: Path) -> set[str]:
    """Names passed as the first argument of ``app.include_router(...)``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "include_router"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "app"):
            continue
        if node.args and isinstance(node.args[0], ast.Name):
            names.add(node.args[0].id)
    return names


def test_main_wires_domains_only_through_api_routers():
    """The composition root must not reach into domain services or repositories."""
    violations = sorted(
        module
        for module in _imported_src_modules(MAIN)
        if module.startswith("src.domains.")
        and module not in _STARTUP_DOMAIN_IMPORTS
        and not module.endswith(".api.routes")
    )
    assert violations == [], (
        "main.py must wire domains through their API routers, not their internals:\n"
        + "\n".join(violations)
    )


def test_main_registers_every_imported_domain_router():
    """An imported-but-unregistered router silently removes a whole API surface."""
    imported = _router_import_aliases(MAIN)
    assert imported, "no domain routers found — the guard has gone stale"
    missing = sorted(imported - _registered_router_names(MAIN))
    assert missing == [], (
        "main.py imports these routers but never calls app.include_router on them:\n"
        + "\n".join(missing)
    )


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
