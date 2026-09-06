"""Additive immutable source metadata; never changes the frozen v1 schema."""

from sqlalchemy import JSON, Column, MetaData, String, Table

metadata = MetaData()
sources = Table(
    "document_sources",
    metadata,
    Column("version_id", String, primary_key=True),
    Column("original_file_name", String, nullable=False),
    Column("original_hash", String, nullable=False),
    Column("original_name", String, nullable=False),
    Column("text_hash", String, nullable=False),
    Column("media_type", String, nullable=False),
    Column("anchors", JSON, nullable=False),
)
