"""Quotes must retain source/catalog permissions through every workflow boundary."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.contracts import Actor, Decision, DocumentACL
from app.db import transaction
from app.errors import DomainError
from app.quote_contracts import QuoteDraft
from app.quotes import Quotes
from app.schema_v1 import tasks


@pytest.fixture
def prepared(ctx):
    service = Quotes(ctx["engine"], ctx["settings"], ctx["knowledge"], ctx["clock"])
    actor = ctx["actors"]["owner"]
    catalog = service.import_catalog(
        actor, "prices.csv", Path("examples/catalogs/synthetic-demo.csv").read_bytes(), "test"
    )
    source = ctx["knowledge"].import_document(
        actor, "private-request.txt", b"STEEL-01 x 3", ["owner"], "test"
    )
    payload = QuoteDraft.model_validate(
        {
            "catalog_version_id": catalog["id"],
            "title": "Private quote",
            "source_document_id": source["document_id"],
            "source_document_version": source["version"],
            "lines": [{"sku": "STEEL-01", "quantity": "3"}],
            "task": {
                "title": "Review quote",
                "team_id": "procurement",
                "assignee_id": "employee",
                "due_at": "2026-09-11T15:00:00+03:00",
                "acceptance_criteria": "Prices checked",
            },
        }
    )
    quote = service.save(actor, payload, "test")
    return service, actor, catalog, source, quote


def decide(ctx, prepared):
    service, actor, _, _, quote = prepared
    proposed = service.propose(actor, quote["id"], 1, "quote-proposed", "test")
    proposal = proposed["proposal"]
    decision = Decision(decision="approve", version=1, payload_hash=proposal["payload_hash"])
    ctx["work"].decide(actor, proposal["id"], decision)
    return proposed


def test_other_roles_cannot_read_or_export_creator_quote(ctx, prepared):
    service, _, _, _, quote = prepared
    for role in ("manager", "employee"):
        with pytest.raises(DomainError):
            service.get(ctx["actors"][role], quote["id"])
        with pytest.raises(DomainError):
            service.export(ctx["actors"][role], quote["id"], "pdf")


def test_cross_org_actor_cannot_access_catalog_or_quote(ctx, prepared):
    service, actor, catalog, _, quote = prepared
    forged = Actor(**{**actor.model_dump(), "organization_id": "other-company"})
    with pytest.raises(DomainError):
        service.catalog(forged, catalog["id"])
    with pytest.raises(DomainError):
        service.get(forged, quote["id"])


def test_revoked_document_blocks_export_run_and_execution(ctx, prepared):
    service, actor, _, source, quote = prepared
    proposed = decide(ctx, prepared)
    ctx["knowledge"].update_acl(
        actor, source["document_id"], DocumentACL(roles=["owner"], revoked=True), "test"
    )
    with pytest.raises(DomainError):
        service.export(actor, quote["id"], "pdf")
    with pytest.raises(DomainError):
        ctx["work"].get(actor, proposed["run"]["id"])
    assert ctx["work"].process_one()
    with ctx["engine"].connect() as conn:
        assert not conn.execute(select(tasks)).all()


def test_revoked_catalog_blocks_approval_and_export(ctx, prepared):
    service, actor, catalog, _, quote = prepared
    proposed = service.propose(actor, quote["id"], 1, "quote-proposed", "test")
    service.update_catalog_acl(
        actor, catalog["catalog_id"], DocumentACL(roles=["owner"], revoked=True), "test"
    )
    with pytest.raises(DomainError):
        service.export(actor, quote["id"], "docx")
    with pytest.raises(DomainError):
        ctx["work"].decide(
            actor,
            proposed["proposal"]["id"],
            Decision(
                decision="approve", version=1, payload_hash=proposed["proposal"]["payload_hash"]
            ),
        )


def test_catalog_price_change_after_approval_blocks_execution(ctx, prepared):
    service, actor, catalog, _, quote = prepared
    proposed = decide(ctx, prepared)
    content = (
        Path("examples/catalogs/synthetic-demo.csv").read_bytes().replace(b"100.00", b"200.00")
    )
    service.import_catalog(actor, "prices.csv", content, "test", catalog["catalog_id"])
    assert ctx["work"].process_one()
    run = ctx["work"].get(actor, proposed["run"]["id"])
    assert run["state"] == "failed" and run["result"]["error_code"] == "STALE_CATALOG"
    with ctx["engine"].connect() as conn:
        assert not conn.execute(select(tasks)).all()
    assert (
        service.get(actor, quote["id"])["revision"]["snapshot"]["calculation"]["total"] == "360.00"
    )


def test_assignee_change_and_proposal_tampering_block_execution(ctx, prepared):
    from app.schema_v1 import actors

    _, _, _, _, _quote = prepared
    decide(ctx, prepared)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "employee").values(active=False))
    assert ctx["work"].process_one()
    with ctx["engine"].connect() as conn:
        assert not conn.execute(select(tasks)).all()


def test_stale_actor_role_cannot_preserve_owner_document_access(ctx, prepared):
    from app.schema_v1 import actors

    service, actor, _, _, quote = prepared
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == actor.id).values(role="manager"))
    with pytest.raises(DomainError):
        service.export(actor, quote["id"], "pdf")
