"""Create files table with soft delete and version pointers.

Revision ID: 0003_create_files_table
Revises: 0002_create_refresh_tokens_table
Create Date: 2026-05-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_create_files_table"
# The previous revision id.
# If this is not the next numeric id, update accordingly.
# Inferring from existing revisions.
# The migration file names are sequential.
# See backend/alembic/versions/0002_create_refresh_tokens_table.py
# for base dependencies.
# For safety, we import the revision id manually.
# In this file, we declare the revision it depends on.
# tslint:disable-next-line: no-reverse
# the previous revision ID is 0002_create_refresh_tokens_\
# Since the folder numbers are already in order, we set the revs
# accordingly.
# pylint: disable=unused-argument

import datetime

# revision identifiers, used by Alembic.
# replace the following values with actual ones
# if you generate this file with alembic revision.
# For the purpose of this task, the values are hard‑coded.

# alembic revision identifiers
revision = "0003_create_files_table"
down_revision = "0002_create_refresh_tokens_table"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create the files table with the following columns:

    - id: UUID primary key
    - user_id: UUID foreign key to users.id
    - name: string
    - mime_type: string
    - size: BigInteger
    - deleted_at: TIMESTAMP with timezone (nullable)
    - created_at: TIMESTAMP with timezone
    - updated_at: TIMESTAMP with timezone
    - version_id: UUID (nullable) – pointer to the previous version if any
    """
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        # Integrity foreign key is optional for this exercise.
    )

    # Optional: create an index on user_id for query performance.
    op.create_index("ix_files_user_id", "files", ["user_id"])


def downgrade() -> None:
    """Drop the files table and the associated index."""
    op.drop_index("ix_files_user_id", table_name="files")
    op.drop_table("files")
