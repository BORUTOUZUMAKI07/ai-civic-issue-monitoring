from __future__ import annotations

import pytest

from src.models.user import UserRole
from src.models.issue import IssueStatus, IssueType


def test_user_role_values() -> None:
    assert UserRole.admin == "admin"
    assert UserRole.engineer == "engineer"
    assert UserRole.field_worker == "field_worker"
    assert UserRole.viewer == "viewer"


def test_issue_status_values() -> None:
    assert IssueStatus.reported == "reported"
    assert IssueStatus.assigned == "assigned"
    assert IssueStatus.in_progress == "in_progress"
    assert IssueStatus.resolved == "resolved"
    assert IssueStatus.verified == "verified"
    assert IssueStatus.rejected == "rejected"


def test_issue_type_values() -> None:
    assert IssueType.pothole == "pothole"
    assert IssueType.garbage == "garbage"
    assert IssueType.debris == "debris"
    assert IssueType.waterlogging == "waterlogging"
    assert IssueType.broken_streetlight == "broken_streetlight"
    assert IssueType.sewage == "sewage"
    assert IssueType.road_damage == "road_damage"
