"""Additive quote/catalog schema, independent of frozen initial tables."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()
catalogs = Table(
    "catalogs",
    metadata,
    Column("id", String, primary_key=True),
    Column("organization_id", String, nullable=False),
    Column("name", String, nullable=False),
    Column("roles", JSON, nullable=False),
    Column("revoked", Boolean, nullable=False),
    Column("current_version", Integer, nullable=False),
)
catalog_versions = Table(
    "catalog_versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("catalog_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("source_hash", String, nullable=False),
    Column("rows", JSON, nullable=False),
    Column("created_at", Float, nullable=False),
    UniqueConstraint("catalog_id", "version"),
)
quotes = Table(
    "quotes",
    metadata,
    Column("id", String, primary_key=True),
    Column("organization_id", String, nullable=False),
    Column("actor_id", String, nullable=False),
    Column("current_version", Integer, nullable=False),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)
quote_versions = Table(
    "quote_versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("quote_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("status", String, nullable=False),
    Column("run_id", String),
    Column("created_at", Float, nullable=False),
    UniqueConstraint("quote_id", "version"),
)
