"""Seed realistic demo data for interviews / local development.

Idempotent: safe to run repeatedly. Creates:
  - N demo engineer accounts (role=engineer) + engineer profiles
  - M realistic issues spread across wards with varied types/statuses/timestamps
  - Assignments linking issues to engineers with SLA deadlines

Demo engineers use the password: DemoEngineer@123
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.core.security import hash_password
from src.models.assignment import Assignment, AssignmentStatus
from src.models.engineer import Engineer
from src.models.issue import Issue, IssueStatus
from src.models.user import User, UserRole
from src.models.ward import Ward

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_ENGINEER_PASSWORD = "DemoEngineer@123"

# name, email, ward_index, specialization
DEMO_ENGINEERS = [
    ("Rakesh Patel", "demo_engineer_rakesh@civicpulse.test", 1, "roads"),
    ("Sunita Sharma", "demo_engineer_sunita@civicpulse.test", 6, "sanitation"),
    ("Amit Joshi", "demo_engineer_amit@civicpulse.test", 9, "utilities"),
    ("Pooja Desai", "demo_engineer_pooja@civicpulse.test", 12, "general"),
]

ISSUE_TEMPLATES = [
    # (type, severity, description, coords_offset)
    ("pothole", 4, "Large pothole on the main road near the bus stop, causing traffic slowdown.", 0.003),
    ("garbage", 3, "Garbage pileup on the street corner; uncollected for several days.", 0.004),
    ("debris", 4, "Construction debris left on the footpath after roadwork.", 0.003),
    ("broken_streetlight", 2, "Streetlight not working at night, making the lane unsafe.", 0.005),
    ("waterlogging", 4, "Severe waterlogging after rain; drains are blocked.", 0.004),
    ("sewage", 4, "Open sewage overflow near the residential colony.", 0.003),
    ("road_damage", 4, "Cracked and uneven road surface causing two-wheeler falls.", 0.003),
]

REPORTER_IDS = [1, 17, 19, 20, 21]


async def _get_or_create_engineers(session: AsyncSession, wards: list[Ward]) -> list[Engineer]:
    engineers: list[Engineer] = []
    for full_name, email, ward_idx, specialization in DEMO_ENGINEERS:
        existing_user = await session.execute(select(User).where(User.email == email))
        user = existing_user.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(DEMO_ENGINEER_PASSWORD),
                full_name=full_name,
                role=UserRole.engineer,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            logger.info("Created demo engineer user: %s (%s)", full_name, email)

        existing_profile = await session.execute(
            select(Engineer).where(Engineer.user_id == user.id)
        )
        profile = existing_profile.scalar_one_or_none()
        if profile is None:
            profile = Engineer(
                user_id=user.id,
                ward_id=wards[ward_idx % len(wards)].id,
                specialization=specialization,
                current_workload=0,
                max_workload=10,
                is_available=True,
            )
            session.add(profile)
            await session.flush()
            logger.info("Created engineer profile for %s", full_name)
        engineers.append(profile)
    return engineers


async def seed_demo() -> None:
    engine = create_async_engine(settings.ASYNC_DATABASE_URI)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        wards = (await session.execute(select(Ward).order_by(Ward.id))).scalars().all()
        if not wards:
            logger.error("No wards found. Run `pixi run seed` first.")
            return

        engineers = await _get_or_create_engineers(session, wards)
        await session.commit()

        existing_count = (
            await session.execute(select(Issue.id).where(Issue.description.like("[DEMO] %")))
        ).all()
        if existing_count:
            logger.info(
                "Found %d existing demo issues; skipping issue seeding (rerun remove to reseed).",
                len(existing_count),
            )
            return

        rng = random.Random(42)
        now = datetime.now(timezone.utc)
        issue_statuses = [
            IssueStatus.reported,
            IssueStatus.reported,
            IssueStatus.assigned,
            IssueStatus.assigned,
            IssueStatus.in_progress,
            IssueStatus.resolved,
        ]

        for i in range(28):
            ward = rng.choice(wards)
            issue_type, severity, desc, off = rng.choice(ISSUE_TEMPLATES)
            age_hours = rng.uniform(1, 30 * 24)

            # Give some already-resolved issues a plausible resolution time window
            created_at = now - timedelta(hours=age_hours)
            status = rng.choice(issue_statuses)

            issue = Issue(
                issue_type=issue_type,
                confidence=round(rng.uniform(0.72, 0.99), 2),
                severity=severity,
                status=status,
                latitude=ward.center_lat + rng.uniform(-off, off),
                longitude=ward.center_lon + rng.uniform(-off, off),
                description=f"[DEMO] {desc}",
                image_url="/uploads/issues/demo_placeholder.jpg",
                review_required=rng.random() < 0.15,
                model_used="mobilenet_v2_onnx",
                probabilities={
                    str(issue_type): round(rng.uniform(0.6, 0.95), 2),
                    "debris": round(rng.uniform(0.0, 0.1), 2),
                    "garbage": round(rng.uniform(0.0, 0.1), 2),
                    "non_civic": round(rng.uniform(0.0, 0.08), 2),
                    "pothole": round(rng.uniform(0.0, 0.1), 2),
                },
                ward_id=ward.id,
                reporter_id=rng.choice(REPORTER_IDS),
                created_at=created_at,
                resolved_at=(created_at + timedelta(hours=rng.uniform(6, 48))) if status == IssueStatus.resolved else None,
            )
            session.add(issue)
            await session.flush()

            # Create assignments for issues that are assigned/in-progress/resolved
            if status in (IssueStatus.assigned, IssueStatus.in_progress, IssueStatus.resolved):
                eng = rng.choice(engineers)
                assigned_at = created_at + timedelta(hours=rng.uniform(0.5, 6))
                a_status = (
                    AssignmentStatus.completed
                    if status == IssueStatus.resolved
                    else (AssignmentStatus.in_progress if status == IssueStatus.in_progress else AssignmentStatus.pending)
                )
                assignment = Assignment(
                    issue_id=issue.id,
                    engineer_id=eng.id,
                    status=a_status,
                    assigned_at=assigned_at,
                    sla_deadline=assigned_at + timedelta(hours=48),
                    accepted_at=assigned_at + timedelta(minutes=30) if a_status != AssignmentStatus.pending else None,
                    completed_at=(
                        assigned_at + timedelta(hours=rng.uniform(4, 40))
                        if a_status == AssignmentStatus.completed
                        else None
                    ),
                )
                session.add(assignment)

        await session.commit()
        logger.info("Demo data seeded: %d issues and assignments.", 28)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_demo())
