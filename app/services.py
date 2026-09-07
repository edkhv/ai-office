import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.auth import get_actor, issue_credential, require, write_private
from app.db import digest, record, row, rows, transaction
from app.errors import DomainError
from app.metrics import calculate
from app.schema_v1 import actors, ledger
from app.workflows import task_counts, task_list
from app.workspace import initialize, profile
from app.workspace_schema import user_profiles

FIXTURE_AS_OF = "2026-09-07T09:00:00+03:00"


def seed(engine, settings, knowledge, now):
    initialize(engine, settings, now)
    if settings.data_mode != "demo":
        return
    root = Path("examples/fixtures")
    with transaction(engine) as conn:
        for name, role, team in [
            ("owner", "owner", "operations"),
            ("manager", "manager", "procurement"),
            ("employee", "employee", "procurement"),
        ]:
            if not row(conn, select(actors).where(actors.c.id == name)):
                conn.execute(
                    actors.insert().values(
                        id=name, organization_id="northline", role=role, team_id=team, active=True
                    )
                )
        fixture = json.loads((root / "ledger.json").read_text())
        for r in fixture["records"]:
            if not row(conn, select(ledger).where(ledger.c.id == r["id"])):
                payload = {
                    **r,
                    "synthetic": True,
                    "as_of": fixture["as_of"],
                    "fixture_version": fixture["fixture_version"],
                }
                conn.execute(
                    ledger.insert().values(
                        id=r["id"],
                        organization_id="northline",
                        payload=payload,
                        content_hash=digest(payload),
                    )
                )
        for item in rows(conn, select(actors)):
            if not row(conn, select(user_profiles).where(user_profiles.c.actor_id == item["id"])):
                conn.execute(
                    user_profiles.insert().values(actor_id=item["id"], display_name=item["id"])
                )
        available_owner = row(
            conn,
            select(actors)
            .where(
                actors.c.organization_id == "northline",
                actors.c.active.is_(True),
                actors.c.role == "owner",
            )
            .order_by(actors.c.id),
        )
        owner = get_actor(conn, available_owner["id"]) if available_owner else None
        active_ids = {
            item["id"] for item in rows(conn, select(actors).where(actors.c.active.is_(True)))
        }
    for name in ("owner", "manager", "employee"):
        path = settings.data_dir / f"{name}.token"
        if name in active_ids and not path.exists():
            write_private(path, issue_credential(engine, settings, name, now) + "\n")
    if owner is None:
        return
    # Do not restore revoked ACLs or overwrite edited documents on subsequent starts.
    existing = {d["name"] for d in knowledge.list_documents(owner)}
    from app.schema_v1 import documents

    with engine.connect() as conn:
        existing = {
            d["name"]
            for d in rows(conn, select(documents))
            if d["current_version"] > 0 or d["revoked"]
        }
    for path in sorted((root / "documents").iterdir()):
        if path.name not in existing:
            knowledge.import_document(
                owner,
                path.name,
                path.read_bytes(),
                ["owner"] if path.name == "restricted.txt" else ["owner", "manager", "employee"],
                "seed",
                observed_at=FIXTURE_AS_OF,
            )


def metrics(engine, actor, now):
    require(actor, "owner", "manager")
    with engine.connect() as conn:
        source = rows(conn, select(ledger).where(ledger.c.organization_id == actor.organization_id))
    with engine.connect() as conn:
        workspace = profile(conn)
    if workspace and workspace["data_mode"] == "pilot":
        return []
    records = [{**r["payload"], "content_hash": r["content_hash"]} for r in source]
    return [
        m.model_dump() for m in calculate(records, FIXTURE_AS_OF, datetime.fromtimestamp(now, UTC))
    ]


def lineage(engine, actor, metric_id, now):
    result = next((m for m in metrics(engine, actor, now) if m["metric_id"] == metric_id), None)
    if not result:
        raise DomainError("NOT_FOUND", 404)
    with engine.connect() as conn:
        sources = rows(
            conn,
            select(ledger).where(
                ledger.c.organization_id == actor.organization_id,
                ledger.c.id.in_([r["record_id"] for r in result["input_refs"]]),
            ),
        )
    return {
        "metric": result,
        "records": [{**s["payload"], "content_hash": s["content_hash"]} for s in sources],
        "assumptions": [
            "Synthetic records only",
            "Contract value is not cash received",
            "No exchange rates or external accounting connectors",
        ],
    }


def briefing(engine, actor, now, correlation_id, timezone="UTC"):
    with engine.connect() as conn:
        workspace = profile(conn)
    synthetic = not workspace or workspace["data_mode"] == "demo"
    facts = metrics(engine, actor, now)
    visible_tasks = task_list(engine, actor, now=now, timezone=timezone)
    counts = task_counts(engine, actor, now, timezone)
    value = {
        "generated_at": datetime.fromtimestamp(now, UTC).isoformat(),
        "source_as_of": FIXTURE_AS_OF if synthetic else None,
        "engine": "deterministic_facts",
        "synthetic": synthetic,
        "finance_synthetic": synthetic,
        "finance_status": "synthetic" if synthetic else "unavailable",
        "task_data": "stored_workflow_records",
        "timezone": timezone,
        "task_counts": counts,
        "task_refs": [
            {
                "task_id": task["id"],
                "source_run_id": task["source_run_id"],
                "url": f"/api/v1/tasks/{task['id']}",
            }
            for task in visible_tasks
        ],
        "facts": facts,
        "tasks": visible_tasks,
        "suggestions": ["Review overdue and upcoming tasks. Suggestions do not execute actions."],
        "limitations": [
            "On demand only; no scheduler or external sending",
            "Task details show first 50; counters include all visible tasks. Use Tasks pagination for all records.",
            "Financial metrics are synthetic; task counters reflect stored workflow records."
            if synthetic
            else "No accounting source is connected; financial metrics are unavailable.",
        ],
    }
    with transaction(engine) as conn:
        record(
            conn,
            actor,
            "briefing",
            actor.id,
            "succeeded",
            correlation_id,
            {"metrics": len(facts)},
            now=now,
        )
    return value
