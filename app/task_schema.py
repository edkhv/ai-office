"""Supplementary task assignment schema; initial task table remains unchanged."""

from sqlalchemy import Column, MetaData, String, Table

metadata = MetaData()
task_assignments = Table(
    "task_assignments",
    metadata,
    Column("task_id", String, primary_key=True),
    Column("assignee_id", String, nullable=True, index=True),
)
