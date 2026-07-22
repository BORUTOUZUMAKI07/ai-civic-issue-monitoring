"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role_enum = postgresql.ENUM("admin", "engineer", "field_worker", "viewer", name="userrole", create_type=False)
    issue_type_enum = postgresql.ENUM(
        "pothole", "garbage", "debris", "waterlogging", "broken_streetlight", "sewage", "road_damage",
        name="issuetype", create_type=False,
    )
    issue_status_enum = postgresql.ENUM(
        "reported", "assigned", "in_progress", "resolved", "verified", "rejected",
        name="issuestatus", create_type=False,
    )
    assignment_status_enum = postgresql.ENUM(
        "pending", "accepted", "in_progress", "completed",
        name="assignmentstatus", create_type=False,
    )

    user_role_enum.create(op.get_bind(), checkfirst=True)
    issue_type_enum.create(op.get_bind(), checkfirst=True)
    issue_status_enum.create(op.get_bind(), checkfirst=True)
    assignment_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(), unique=True, index=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("role", user_role_enum, server_default="field_worker"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "wards",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), unique=True, nullable=False),
        sa.Column("polygon", postgresql.JSONB(), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "engineers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("ward_id", sa.Integer(), sa.ForeignKey("wards.id"), nullable=False),
        sa.Column("specialization", sa.String(), server_default="general"),
        sa.Column("current_workload", sa.Integer(), server_default="0"),
        sa.Column("max_workload", sa.Integer(), server_default="10"),
        sa.Column("is_available", sa.Boolean(), server_default="true"),
        sa.Column("avg_resolution_hours", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("issue_type", issue_type_enum, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("status", issue_status_enum, server_default="reported"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=False),
        sa.Column("review_required", sa.Boolean(), server_default="false"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("ward_id", sa.Integer(), sa.ForeignKey("wards.id"), nullable=False),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id"), nullable=False),
        sa.Column("engineer_id", sa.Integer(), sa.ForeignKey("engineers.id"), nullable=False),
        sa.Column("status", assignment_status_enum, server_default="pending"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "resolutions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issues.id"), unique=True, nullable=False),
        sa.Column("engineer_id", sa.Integer(), sa.ForeignKey("engineers.id"), nullable=False),
        sa.Column("before_image_url", sa.String(), nullable=False),
        sa.Column("after_image_url", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("similarity_score", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("resolutions")
    op.drop_table("assignments")
    op.drop_table("issues")
    op.drop_table("engineers")
    op.drop_table("wards")
    op.drop_table("users")

    postgresql.ENUM(name="assignmentstatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="issuestatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="issuetype").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="userrole").drop(op.get_bind(), checkfirst=True)
