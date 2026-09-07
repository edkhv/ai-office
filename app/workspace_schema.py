"""Workspace metadata; separate from the frozen original schema."""

from sqlalchemy import Boolean, CheckConstraint, Column, Float, MetaData, String, Table

metadata = MetaData()
workspace_profiles = Table(
    "workspace_profiles",
    metadata,
    Column("id", String, primary_key=True),
    Column("organization_id", String, unique=True, nullable=True),
    Column("company_name", String, nullable=True),
    Column("timezone", String, nullable=False),
    Column("data_mode", String, nullable=False),
    Column("setup_digest", String, nullable=True),
    Column("setup_completed", Boolean, nullable=False),
    Column("created_at", Float, nullable=False),
    CheckConstraint("id = 'workspace'", name="single_workspace"),
)
user_profiles = Table(
    "user_profiles",
    metadata,
    Column("actor_id", String, primary_key=True),
    Column("display_name", String, nullable=False),
)
