"""add import task status

Revision ID: f3b8d1c6a2e4
Revises: e2a7c9d4f6b1
Create Date: 2026-11-13 01:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b8d1c6a2e4"
down_revision: Union[str, Sequence[str], None] = "e2a7c9d4f6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Track whether an import is running, completed or failed."""
    op.add_column(
        "import_tasks",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="completed"),
    )


def downgrade() -> None:
    """Drop the import status column."""
    op.drop_column("import_tasks", "status")
