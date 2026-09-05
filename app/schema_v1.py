"""Frozen initial schema shared with migration 0001; add later changes in new migrations."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()


def table(name, *columns, constraints=()):
    return Table(name, metadata, Column("id", String, primary_key=True), *columns, *constraints)


actors = table(
    "actors",
    Column("organization_id", String, nullable=False),
    Column("role", String, nullable=False),
    Column("team_id", String, nullable=False),
    Column("active", Boolean, nullable=False),
)
credentials = table(
    "credentials",
    Column("actor_id", String, nullable=False),
    Column("digest", String, unique=True, nullable=False),
    Column("expires_at", Float, nullable=False),
    Column("revoked", Boolean, nullable=False),
)
sessions = table(
    "sessions",
    Column("actor_id", String, nullable=False),
    Column("credential_id", String, nullable=False),
    Column("digest", String, unique=True, nullable=False),
    Column("csrf_digest", String, nullable=False),
    Column("expires_at", Float, nullable=False),
)
login_limits = table(
    "login_limits",
    Column("attempts", Integer, nullable=False),
    Column("reset_at", Float, nullable=False),
)
runs = table(
    "runs",
    Column("organization_id", String, nullable=False),
    Column("actor_id", String, nullable=False),
    Column("type", String, nullable=False),
    Column("state", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("input", JSON, nullable=False),
    Column("result", JSON),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
    Column("correlation_id", String, nullable=False),
    Column("idempotency_key", String, nullable=False),
    Column("input_hash", String, nullable=False),
    constraints=(UniqueConstraint("actor_id", "idempotency_key"),),
)
jobs = table(
    "jobs",
    Column("run_id", String, nullable=False),
    Column("stage", String, nullable=False),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("lease_until", Float, nullable=False),
    Column("lease_token", String),
    Column("next_attempt_at", Float, nullable=False),
    Column("error_code", String),
    constraints=(UniqueConstraint("run_id", "stage"),),
)
proposals = table(
    "proposals",
    Column("run_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("payload_hash", String, nullable=False),
    Column("expires_at", Float, nullable=False),
    Column("status", String, nullable=False),
)
approvals = table(
    "approvals",
    Column("proposal_id", String, unique=True, nullable=False),
    Column("actor_id", String, nullable=False),
    Column("decision", String, nullable=False),
    Column("payload_hash", String, nullable=False),
    Column("expires_at", Float, nullable=False),
    Column("executed_at", Float),
)
tasks = table(
    "tasks",
    Column("organization_id", String, nullable=False),
    Column("title", Text, nullable=False),
    Column("team_id", String, nullable=False),
    Column("due_at", String, nullable=False),
    Column("acceptance_criteria", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("result", Text, nullable=False),
    Column("source_run_id", String, nullable=False),
    Column("slot", Integer, nullable=False),
    constraints=(UniqueConstraint("source_run_id", "slot"),),
)
documents = table(
    "documents",
    Column("organization_id", String, nullable=False),
    Column("name", String, nullable=False),
    Column("roles", JSON, nullable=False),
    Column("revoked", Boolean, nullable=False),
    Column("current_version", Integer, nullable=False),
)
versions = table(
    "document_versions",
    Column("document_id", String, nullable=False),
    Column("version", Integer, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("state", String, nullable=False),
    Column("file_name", String, nullable=False),
    Column("observed_at", String, nullable=False),
    Column("index_name", String),
    constraints=(UniqueConstraint("document_id", "version"),),
)
ledger = table(
    "ledger",
    Column("organization_id", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("content_hash", String, nullable=False),
)
audit = table(
    "audit",
    Column("actor_id", String, nullable=False),
    Column("organization_id", String, nullable=False),
    Column("action", String, nullable=False),
    Column("target", String, nullable=False),
    Column("outcome", String, nullable=False),
    Column("safe_diff", JSON, nullable=False),
    Column("timestamp", Float, nullable=False),
    Column("correlation_id", String, nullable=False),
)
heartbeats = table("heartbeats", Column("seen_at", Float, nullable=False))
