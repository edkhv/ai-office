"""Preserved original document bytes and stable extraction anchors."""

from alembic import op

from app.document_schema import metadata

revision = "0002_documents"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
