"""drop redundant indexes

Revision ID: c4f1a2b3d5e6
Revises: 3e0cbadc8330
Create Date: 2026-11-12 00:00:00.000000

The dropped indexes duplicate primary keys or primary-key prefixes, or have
too little selectivity to be useful for the current query patterns.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f1a2b3d5e6"
down_revision: Union[str, Sequence[str], None] = "3e0cbadc8330"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REDUNDANT_INDEXES: tuple[str, ...] = (
    "ix_title_ratings_tconst",
    "ix_episodes_tconst",
    "ix_title_akas_title_id",
    "ix_title_principals_tconst",
    "ix_title_principals_category",
)


def upgrade() -> None:
    """Drop indexes that duplicate primary keys or are not selective enough."""
    for index_name in REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    """Recreate the indexes dropped in upgrade()."""
    op.create_index("ix_title_ratings_tconst", "title_ratings", ["tconst"], unique=False)
    op.create_index("ix_episodes_tconst", "episodes", ["tconst"], unique=False)
    op.create_index("ix_title_akas_title_id", "title_akas", ["title_id"], unique=False)
    op.create_index("ix_title_principals_tconst", "title_principals", ["tconst"], unique=False)
    op.create_index("ix_title_principals_category", "title_principals", ["category"], unique=False)
