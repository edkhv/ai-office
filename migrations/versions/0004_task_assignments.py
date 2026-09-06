"""Add optional individual task assignees without rewriting existing tasks."""

from alembic import op

from app.task_schema import metadata

revision = "0004_task_assignments"
down_revision = "0003_quotes"
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
