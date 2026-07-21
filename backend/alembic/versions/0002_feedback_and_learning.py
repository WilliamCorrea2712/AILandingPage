"""Add feedback fields to ai_generations and pattern_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2024-06-01 00:00:00.000000

- Adds user_rating (smallint: 1=positive, -1=negative) to ai_generations
- Adds feedback_text (text, optional) to ai_generations
- Adds niche field to ai_generations for fast pattern queries
- Creates pattern_cache table for auto-learned niche patterns
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add feedback fields to ai_generations
    op.add_column("ai_generations",
        sa.Column("user_rating", sa.SmallInteger(), nullable=True))
    op.add_column("ai_generations",
        sa.Column("feedback_text", sa.Text(), nullable=True))
    op.add_column("ai_generations",
        sa.Column("niche", sa.String(100), nullable=True))
    op.add_column("ai_generations",
        sa.Column("feedback_at", TIMESTAMP(timezone=True), nullable=True))

    # Create pattern_cache table — stores auto-learned niche patterns
    op.create_table(
        "pattern_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("niche", sa.String(100), nullable=False, index=True),
        sa.Column("pattern_type", sa.String(50), nullable=False),
        # e.g. "service", "differential", "testimonial", "faq", "cta"
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Integer(), server_default="1", default=1),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("niche", "pattern_type", "value",
                            name="uq_pattern_cache_niche_type_value"),
    )


def downgrade() -> None:
    op.drop_table("pattern_cache")
    op.drop_column("ai_generations", "feedback_at")
    op.drop_column("ai_generations", "niche")
    op.drop_column("ai_generations", "feedback_text")
    op.drop_column("ai_generations", "user_rating")
