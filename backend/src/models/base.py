"""Compatibility shim.

The canonical SQLAlchemy declarative ``Base`` now lives in
``src.shared.base``. This module re-exports it so existing imports such as
``from src.models.base import Base`` keep working (notably the protected
``tests/conftest.py`` and ``src.models`` registration path).
"""

from src.shared.base import Base

__all__ = ["Base"]
