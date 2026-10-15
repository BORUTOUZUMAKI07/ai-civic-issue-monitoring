"""Compatibility shim.

The canonical ``User`` / ``UserRole`` now live in
``src.domains.users.models.user``. This re-export keeps the historical
``from src.models.user import ...`` path working (the protected
``tests/conftest.py`` relies on it).
"""

from src.domains.users.models.user import User, UserRole

__all__ = ["User", "UserRole"]
