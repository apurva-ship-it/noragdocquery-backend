"""Create document_chunks table for the noRAG document query feature.

Revision ID: 0005_create_documents_tables
Revises: 0004_create_file_versions_table
Create Date: 2026-05-12 00:00:00.000000
"""
from __future__ import annotations

import datetime
import sqlalchemy as sa
from alembic import op

revision = "0005_create_documents_tables"
down_revision = "0004_create_file_versions_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            default=datetime.datetime.utcnow,
        ),
    )
    op.create_index("ix_document_chunks_document_name", "document_chunks", ["document_name"])
    op.create_index("ix_document_chunks_order_index", "document_chunks", ["order_index"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_order_index", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_name", table_name="document_chunks")
    op.drop_table("document_chunks")
