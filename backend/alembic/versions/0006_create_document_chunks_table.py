"""Placeholder migration to avoid duplicate table creation.

Revision ID: 0006_create_document_chunks_table
Revises: 0005_create_documents_tables
Create Date: 2026-05-12 01:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "0006_create_document_chunks_table"
down_revision = "0005_create_documents_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No operation; document_chunks table is created in revision 0005.
    pass


def downgrade() -> None:
    # No operation; downgrade handled in revision 0005.
    pass
