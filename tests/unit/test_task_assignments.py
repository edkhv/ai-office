from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.contracts import Clarification, TaskUpdate
from app.db import transaction
from app.errors import DomainError
from app.schema_v1 import actors, tasks
from app.services import briefing
from app.task_schema import task_assignments
from app.workflows import allowable_assignees, task_counts, task_list, update_task
from tests.conftest import COMMAND
from tests.unit.test_workflows import approve, task_count


def assigned_plan(ctx, assignee_id="employee"):
    run = ctx["work"].submit(
        ctx["actors"]["owner"], {**COMMAND, "assignee_id": assignee_id}, "assigned", "test"
    )
    ctx["work"].process_one()
    return ctx["work"].get(ctx["actors"]["owner"], run["id"])


def test_user_assignment_is_persisted_and_replay_safe(ctx):
    run = assigned_plan(ctx)
    assert all(t["assignee_id"] == "employee" for t in run["proposal"]["payload"]["proposed_tasks"])
    approve(ctx, run)
    ctx["work"].process_one()
    assert approve(ctx, run)["replayed"]
    visible = task_list(ctx["engine"], ctx["actors"]["employee"], mine=True)
    assert len(visible) == 3
    assert task_counts(ctx["engine"], ctx["actors"]["employee"], ctx["clock"]())["mine"] == 3
    assert all(t["assignee_id"] == "employee" for t in visible)


@pytest.mark.parametrize(
    "change", [{"active": False}, {"organization_id": "elsewhere"}, {"team_id": "operations"}]
)
def test_invalid_assignee_blocks_approval(ctx, change):
    run = assigned_plan(ctx)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "employee").values(**change))
    with pytest.raises(DomainError, match="INVALID_ASSIGNEE"):
        approve(ctx, run)
    assert task_count(ctx) == 0


@pytest.mark.parametrize(
    "change", [{"active": False}, {"organization_id": "elsewhere"}, {"team_id": "operations"}]
)
def test_invalid_assignee_after_approval_blocks_execution(ctx, change):
    run = assigned_plan(ctx)
    approve(ctx, run)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "employee").values(**change))
    ctx["work"].process_one()
    assert ctx["work"].get(ctx["actors"]["owner"], run["id"])["state"] == "failed"
    assert task_count(ctx) == 0


def test_assignment_revision_invalidates_approval(ctx):
    run = assigned_plan(ctx)
    approve(ctx, run)
    ctx["work"].clarify(
        ctx["actors"]["owner"],
        run["id"],
        Clarification(
            version=1, team_id="procurement", due_at=COMMAND["due_at"], assignee_id="manager"
        ),
    )
    assert task_count(ctx) == 0
    ctx["work"].process_one()
    revised = ctx["work"].get(ctx["actors"]["owner"], run["id"])
    assert revised["proposal"]["payload_hash"] != run["proposal"]["payload_hash"]
    assert revised["proposal"]["payload"]["proposed_tasks"][0]["assignee_id"] == "manager"
    with pytest.raises(DomainError, match="VERSION_CONFLICT"):
        approve(ctx, run)


def test_assignee_controls_update_but_team_retains_visibility(ctx):
    run = assigned_plan(ctx, "manager")
    approve(ctx, run)
    ctx["work"].process_one()
    employee = ctx["actors"]["employee"]
    visible = task_list(ctx["engine"], employee)
    assert len(visible) == 3
    update = TaskUpdate(status="done", result="Completed")
    with pytest.raises(DomainError, match="FORBIDDEN"):
        update_task(ctx["engine"], employee, visible[0]["id"], update, "test", ctx["clock"]())
    update_task(
        ctx["engine"], ctx["actors"]["owner"], visible[0]["id"], update, "test", ctx["clock"]()
    )
    with transaction(ctx["engine"]) as conn:
        conn.execute(
            task_assignments.delete().where(task_assignments.c.task_id == visible[1]["id"])
        )
    update_task(ctx["engine"], employee, visible[1]["id"], update, "test", ctx["clock"]())


def add_tasks(ctx, due_dates):
    with transaction(ctx["engine"]) as conn:
        for slot, (due_at, status, team, org) in enumerate(due_dates):
            conn.execute(
                tasks.insert().values(
                    id=f"test-{slot}",
                    organization_id=org,
                    title=f"Task {slot}",
                    team_id=team,
                    due_at=due_at,
                    acceptance_criteria="Review result",
                    status=status,
                    result="",
                    source_run_id="manual-test",
                    slot=slot,
                )
            )


def test_counts_include_all_pages_and_scope(ctx):
    add_tasks(
        ctx,
        [("2026-09-06T12:00:00+00:00", "todo", "procurement", "northline")] * 65
        + [
            ("2026-09-06T12:00:00+00:00", "todo", "operations", "northline"),
            ("2026-09-06T12:00:00+00:00", "todo", "procurement", "elsewhere"),
        ],
    )
    employee = ctx["actors"]["employee"]
    assert len(task_list(ctx["engine"], employee)) == 50
    assert len(task_list(ctx["engine"], employee, offset=50)) == 15
    counts = task_counts(ctx["engine"], employee, ctx["clock"]())
    assert counts["total"] == counts["overdue"] == 65
    value = briefing(ctx["engine"], ctx["actors"]["owner"], ctx["clock"](), "test")
    assert len(value["tasks"]) == 50
    assert value["task_counts"]["total"] == 66
    assert value["finance_synthetic"] is True
    assert value["task_data"] == "stored_workflow_records"
    assert all(ref["task_id"] for ref in value["task_refs"])


def test_clock_boundary_timezone_and_completed_exclusion(ctx):
    # Server now 06:00Z; offsets in migrated records must compare as instants.
    add_tasks(
        ctx,
        [
            ("2026-09-07T09:00:00+03:00", "todo", "procurement", "northline"),
            ("2026-09-07T08:59:59+03:00", "blocked", "procurement", "northline"),
            ("2026-09-07T01:00:00+03:00", "done", "procurement", "northline"),
            ("2026-09-08T00:00:00+03:00", "todo", "procurement", "northline"),
        ],
    )
    who = ctx["actors"]["employee"]
    counts = task_counts(ctx["engine"], who, ctx["clock"](), "Europe/Moscow")
    assert counts["overdue"] == 1
    assert counts["today"] == 2
    assert counts["blocked"] == 1
    assert counts["done"] == 1
    assert (
        len(
            task_list(ctx["engine"], who, due="today", timezone="Europe/Moscow", now=ctx["clock"]())
        )
        == 2
    )
    assert task_counts(ctx["engine"], who, ctx["clock"](), "America/Los_Angeles")["today"] == 2
    ctx["clock"].value += 1
    assert task_counts(ctx["engine"], who, ctx["clock"]())["overdue"] == 2


def test_dst_and_invalid_timezone(ctx):
    from app.workflows import deadline_bounds

    now = datetime(2026, 3, 8, 16, tzinfo=UTC).timestamp()
    _, start, end = deadline_bounds(now, "America/New_York")
    assert (
        datetime.fromisoformat(end) - datetime.fromisoformat(start)
    ).total_seconds() == 23 * 3600
    with pytest.raises(DomainError, match="INVALID_TIMEZONE"):
        task_counts(ctx["engine"], ctx["actors"]["owner"], now, "not/a/timezone")


def test_allowable_assignees_returns_no_credentials_and_only_active_team(ctx):
    visible = allowable_assignees(ctx["engine"], ctx["actors"]["owner"], "procurement")
    assert {a["id"] for a in visible} == {"manager", "employee"}
    assert all(set(a) == {"id", "role", "team_id"} for a in visible)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "employee").values(active=False))
    assert [a["id"] for a in allowable_assignees(ctx["engine"], ctx["actors"]["employee"])] == [
        "manager"
    ]


def test_migration_preserves_initial_tasks(tmp_path):
    from alembic import command
    from alembic.config import Config

    from app.config import Settings
    from app.db import engine_for, migrate

    settings = Settings(data_dir=tmp_path / "old-data", _env_file=None)
    settings.data_dir.mkdir()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "0001")
    engine = engine_for(settings)
    with transaction(engine) as conn:
        conn.execute(
            tasks.insert().values(
                id="legacy",
                organization_id="northline",
                title="Legacy task",
                team_id="procurement",
                due_at="2026-09-11T12:00:00+00:00",
                acceptance_criteria="Review",
                status="todo",
                result="",
                source_run_id="legacy-run",
                slot=0,
            )
        )
    migrate(settings)
    with engine.connect() as conn:
        assert conn.scalar(select(tasks.c.title).where(tasks.c.id == "legacy")) == "Legacy task"
        assert conn.scalar(select(task_assignments.c.task_id)) is None
    engine.dispose()


def test_task_filter_and_assignee_api_auth_and_scope(ctx, owner_headers, employee_headers):
    run = assigned_plan(ctx, "manager")
    approve(ctx, run)
    ctx["work"].process_one()
    client = ctx["client"]
    for path in ("/api/v1/tasks/counts", "/api/v1/tasks/assignees"):
        assert client.get(path).status_code == 401
    visible = client.get("/api/v1/tasks", headers=employee_headers).json()
    assert len(visible) == 3
    assert client.get("/api/v1/tasks?mine=true", headers=employee_headers).json() == []
    counts = client.get("/api/v1/tasks/counts?assignee_id=manager", headers=owner_headers).json()
    assert counts["filtered"] == 3
    assert (
        client.get("/api/v1/tasks/counts?timezone=Invalid", headers=owner_headers).status_code
        == 422
    )
    assert client.get("/api/v1/tasks?due=never", headers=owner_headers).status_code == 422
    assert {
        a["id"] for a in client.get("/api/v1/tasks/assignees", headers=employee_headers).json()
    } == {"manager", "employee"}
    assert (
        client.patch(
            f"/api/v1/tasks/{visible[0]['id']}", headers=employee_headers, json={"status": "done"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/briefings?timezone=Europe/Moscow", headers=owner_headers).json()[
            "timezone"
        ]
        == "Europe/Moscow"
    )


def test_original_download_preserves_unicode_filename_and_current_acl(
    ctx, owner_headers, employee_headers
):
    client = ctx["client"]
    source = "Условия заказа и сроки поставки".encode()
    response = client.post(
        "/api/v1/documents",
        headers=owner_headers,
        files={"file": ("Заявка.txt", source, "text/plain")},
    )
    assert response.status_code == 200
    document_id = response.json()["document_id"]
    url = f"/api/v1/documents/{document_id}/original?version=1"
    assert client.get(url).status_code == 401
    original = client.get(url, headers=employee_headers)
    assert original.status_code == 200
    assert original.content == source
    assert "filename*=UTF-8''%D0%97" in original.headers["Content-Disposition"]
    assert original.headers["X-Original-Preserved"] == "true"
    assert (
        client.patch(
            f"/api/v1/documents/{document_id}/acl",
            headers=owner_headers,
            json={"roles": ["owner"], "revoked": False},
        ).status_code
        == 200
    )
    assert client.get(url, headers=employee_headers).status_code == 404


def test_binary_request_limit_does_not_expand_text_or_command_limits(ctx, owner_headers):
    from io import BytesIO

    from reportlab.pdfgen import canvas

    output = BytesIO()
    pdf = canvas.Canvas(output, pageCompression=0)
    pdf.drawString(50, 700, "Request STEEL-01 quantity 5")
    pdf.save()
    # Valid trailing PDF comments exceed the text cap but stay under the binary cap.
    data = output.getvalue() + b"\n% harmless comment\n" * 8000
    assert len(data) > ctx["settings"].max_upload_bytes
    client = ctx["client"]
    assert (
        client.post(
            "/api/v1/documents",
            headers=owner_headers,
            files={"file": ("request.pdf", data, "application/pdf")},
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/documents",
        headers=owner_headers,
        files={"file": ("large.txt", b"x" * (ctx["settings"].max_upload_bytes + 1), "text/plain")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"
    response = client.post(
        "/api/v1/commands",
        headers=owner_headers,
        content=b"x" * (ctx["settings"].max_upload_bytes + 16385),
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_approval_respects_queue_capacity_and_can_be_retried(ctx):
    run = assigned_plan(ctx)
    ctx["settings"].max_queue = 1
    ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "other", "test")
    with pytest.raises(DomainError, match="QUEUE_FULL"):
        approve(ctx, run)
    assert ctx["work"].get(ctx["actors"]["owner"], run["id"])["state"] == "awaiting_approval"
    ctx["work"].process_one()
    approve(ctx, run)
    ctx["work"].process_one()
    assert task_count(ctx) == 3


def test_stale_actor_cannot_keep_approval_or_update_privileges(ctx):
    run = assigned_plan(ctx, "manager")
    cached_owner = ctx["actors"]["owner"]
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "owner").values(role="employee"))
    with pytest.raises(DomainError, match="FORBIDDEN"):
        approve(ctx, run)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "owner").values(role="owner"))
    approve(ctx, run)
    ctx["work"].process_one()
    task = task_list(ctx["engine"], cached_owner)[0]
    with transaction(ctx["engine"]) as conn:
        conn.execute(
            actors.update()
            .where(actors.c.id == "owner")
            .values(role="employee", team_id="procurement")
        )
    with pytest.raises(DomainError, match="FORBIDDEN"):
        update_task(
            ctx["engine"],
            cached_owner,
            task["id"],
            TaskUpdate(status="done"),
            "test",
            ctx["clock"](),
        )


@pytest.mark.parametrize("phase", ["planning", "execution"])
def test_actor_organization_change_cannot_move_run_data_or_tasks(ctx, phase):
    run = ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "org-drift", "test")
    if phase == "execution":
        ctx["work"].process_one()
        run = ctx["work"].get(ctx["actors"]["owner"], run["id"])
        approve(ctx, run)
    with transaction(ctx["engine"]) as conn:
        conn.execute(
            actors.update().where(actors.c.id == "owner").values(organization_id="elsewhere")
        )
    ctx["work"].process_one()
    result = ctx["work"].get(ctx["actors"]["owner"], run["id"])
    assert result["state"] == "failed"
    assert result["result"]["error_code"] == "ACTOR_ORGANIZATION_CHANGED"
    assert task_count(ctx) == 0
