"""Unit tests for the create-admin bootstrap validation.

These exercise the pure guardrails (role + credential validation) that run
*before* any database work, so no DB is required. ``scripts/`` is not an
importable package, so the module is loaded by path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_admin.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_create_admin_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


@pytest.mark.parametrize("role", ["admin", "super_admin", "ADMIN", " Super_Admin "])
def test_resolve_role_accepts_admin_roles(role: str) -> None:
    assert mod.resolve_role(role) in {"admin", "super_admin"}


@pytest.mark.parametrize("role", ["", "engineer", "field_worker", "viewer", "root", "superuser"])
def test_resolve_role_rejects_non_admin_roles(role: str) -> None:
    assert mod.resolve_role(role) is None


def test_validate_credentials_accepts_strong_input() -> None:
    assert mod.validate_credentials("admin@example.com", "a-very-strong-passphrase") is None


@pytest.mark.parametrize("email", ["", "not-an-email", "missing-at.example.com"])
def test_validate_credentials_rejects_bad_email(email: str) -> None:
    assert mod.validate_credentials(email, "a-very-strong-passphrase") is not None


def test_validate_credentials_rejects_missing_password() -> None:
    assert mod.validate_credentials("admin@example.com", "") is not None


def test_validate_credentials_rejects_short_password() -> None:
    assert mod.validate_credentials("admin@example.com", "short") is not None


@pytest.mark.parametrize("password", ["changeme", "password", "Password123", "  Admin  "])
def test_validate_credentials_rejects_placeholders(password: str) -> None:
    assert mod.validate_credentials("admin@example.com", password) is not None
