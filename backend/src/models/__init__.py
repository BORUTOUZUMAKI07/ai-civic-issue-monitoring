"""SQLAlchemy model registry.

Importing this package registers every ORM model on ``Base.metadata`` so that
string-based relationships (``relationship("Ward")``, ``relationship("User")``,
...) and ``Base.metadata.create_all`` resolve. It is intentionally the one
place that pulls models from every domain.

``Base`` is re-exported from the shared kernel for backwards compatibility
(``from src.models import Base``); the canonical declaration lives in
``src.shared.base``.
"""

from src.domains.assignments.models.assignment import Assignment
from src.domains.engineers.models.engineer import Engineer
from src.domains.issues.models.idempotency import IdempotencyKey
from src.domains.issues.models.issue import Issue
from src.domains.resolution.models.resolution import Resolution
from src.domains.users.models.user import User
from src.domains.wards.models.ward import Ward
from src.shared.base import Base

__all__ = ["Base", "User", "Issue", "Ward", "Engineer", "Assignment", "Resolution", "IdempotencyKey"]
