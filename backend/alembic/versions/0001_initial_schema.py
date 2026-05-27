"""Initial schema — 9 tables

Revision ID: 0001
Revises:
Create Date: 2024-01-15 00:00:00.000000

Creates all nine core tables for the WTech Landing Pages platform:
  users, prompts, templates, projects, components, ai_generations,
  training_data, analytics, publications

Requirements: 14.1
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.VARCHAR(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.VARCHAR(255), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column(
            "role",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "is_active",
            sa.BOOLEAN,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )

    # ------------------------------------------------------------------
    # templates  (must exist before projects references it)
    # ------------------------------------------------------------------
    op.create_table(
        "templates",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("description", sa.TEXT, nullable=True),
        sa.Column("visual_style", sa.VARCHAR(50), nullable=False),
        sa.Column("sections", JSONB, nullable=False),
        sa.Column(
            "is_default",
            sa.BOOLEAN,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("embedding_id", sa.VARCHAR(255), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # projects
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("slug", sa.VARCHAR(255), unique=True, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
        ),
    )

    # ------------------------------------------------------------------
    # prompts
    # ------------------------------------------------------------------
    op.create_table(
        "prompts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "content",
            sa.TEXT,
            nullable=False,
            # CHECK constraint: 10 ≤ char_length(content) ≤ 2000
        ),
        sa.Column("nlp_result", JSONB, nullable=True),
        sa.Column(
            "language",
            sa.VARCHAR(10),
            nullable=False,
            server_default=sa.text("'pt'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(content) BETWEEN 10 AND 2000",
            name="ck_prompts_content_length",
        ),
    )

    # ------------------------------------------------------------------
    # components
    # ------------------------------------------------------------------
    op.create_table(
        "components",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("template_id", UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.VARCHAR(50), nullable=False),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("vue_sfc", sa.TEXT, nullable=False),
        sa.Column("props_schema", JSONB, nullable=True),
        sa.Column("embedding_id", sa.VARCHAR(255), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            ondelete="SET NULL",
        ),
    )

    # ------------------------------------------------------------------
    # ai_generations
    # ------------------------------------------------------------------
    op.create_table(
        "ai_generations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column(
            "status",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("structured_json", JSONB, nullable=True),
        sa.Column("html_output", sa.TEXT, nullable=True),
        sa.Column("css_output", sa.TEXT, nullable=True),
        sa.Column("error_details", JSONB, nullable=True),
        sa.Column(
            "retry_count",
            sa.SMALLINT,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"],
            ["prompts.id"],
        ),
    )

    # ------------------------------------------------------------------
    # training_data
    # ------------------------------------------------------------------
    op.create_table(
        "training_data",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("prompt", sa.TEXT, nullable=False),
        sa.Column("completion", sa.TEXT, nullable=False),
        sa.Column(
            "source",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'api'"),
        ),
        sa.Column(
            "quality_score",
            sa.FLOAT,
            nullable=True,
        ),
        sa.Column(
            "is_validated",
            sa.BOOLEAN,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR quality_score BETWEEN 0 AND 1",
            name="ck_training_data_quality_score",
        ),
    )

    # ------------------------------------------------------------------
    # analytics
    # ------------------------------------------------------------------
    op.create_table(
        "analytics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.VARCHAR(100), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="SET NULL",
        ),
    )

    # Indices for analytics (Requirements: 14.1)
    op.create_index("idx_analytics_user_id", "analytics", ["user_id"])
    op.create_index("idx_analytics_event_type", "analytics", ["event_type"])
    op.create_index("idx_analytics_created_at", "analytics", ["created_at"])

    # ------------------------------------------------------------------
    # publications
    # ------------------------------------------------------------------
    op.create_table(
        "publications",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("generation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("subdomain", sa.VARCHAR(255), unique=True, nullable=False),
        sa.Column("custom_domain", sa.VARCHAR(255), nullable=True),
        sa.Column(
            "ssl_status",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "cdn_status",
            sa.VARCHAR(50),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("published_url", sa.VARCHAR(500), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["ai_generations.id"],
        ),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("publications")
    op.drop_index("idx_analytics_created_at", table_name="analytics")
    op.drop_index("idx_analytics_event_type", table_name="analytics")
    op.drop_index("idx_analytics_user_id", table_name="analytics")
    op.drop_table("analytics")
    op.drop_table("training_data")
    op.drop_table("ai_generations")
    op.drop_table("components")
    op.drop_table("prompts")
    op.drop_table("projects")
    op.drop_table("templates")
    op.drop_table("users")
