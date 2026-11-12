"""add trigram and array search indexes

Revision ID: e2a7c9d4f6b1
Revises: c4f1a2b3d5e6
Create Date: 2026-11-13 00:00:00.000000

Search endpoints use ILIKE '%...%', which cannot use a regular B-tree index.
Trigram GIN indexes make those queries indexable. The GIN index on
titles.genres also speeds up genre filters.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a7c9d4f6b1"
down_revision: Union[str, Sequence[str], None] = "c4f1a2b3d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEARCH_INDEXES: tuple[str, ...] = (
    "ix_titles_primary_title_trgm",
    "ix_titles_original_title_trgm",
    "ix_titles_genres_gin",
    "ix_people_primary_name_trgm",
)


def upgrade() -> None:
    """Create pg_trgm and GIN indexes used by search and genre filters."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # Index builds on already populated databases benefit from a larger budget.
    op.execute("SET maintenance_work_mem = '1GB'")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_titles_primary_title_trgm "
        "ON titles USING gin (primary_title gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_titles_original_title_trgm "
        "ON titles USING gin (original_title gin_trgm_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_titles_genres_gin ON titles USING gin (genres)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_people_primary_name_trgm "
        "ON people USING gin (primary_name gin_trgm_ops)"
    )


def downgrade() -> None:
    """Drop the search indexes (the pg_trgm extension is kept)."""
    for index_name in SEARCH_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
