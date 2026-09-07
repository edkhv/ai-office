"""Add single-company metadata without changing existing actors or tasks."""

from alembic import op
from sqlalchemy import text

from app.workspace_schema import metadata

revision = "0005_workspace"
down_revision = "0004_task_assignments"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    metadata.create_all(bind)
    # Existing installations were demo-only; never infer a claim of real company data.
    orgs = bind.execute(text("SELECT DISTINCT organization_id FROM actors")).scalars().all()
    if len(orgs) == 1:
        bind.execute(
            text(
                "INSERT INTO workspace_profiles (id, organization_id, company_name, timezone, data_mode, setup_completed, created_at) VALUES ('workspace', :org, :name, 'Europe/Moscow', 'demo', 1, 0)"
            ),
            {
                "org": orgs[0],
                "name": "Northline Demo" if orgs[0] == "northline" else "Existing demonstration",
            },
        )
    bind.execute(
        text("INSERT INTO user_profiles (actor_id, display_name) SELECT id, id FROM actors")
    )


def downgrade():
    metadata.drop_all(op.get_bind())
