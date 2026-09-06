"""Immutable price catalogs and calculated quote revisions."""

from alembic import op

from app.quote_schema import metadata

revision = "0003_quotes"
down_revision = "0002_documents"
branch_labels = None
depends_on = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
