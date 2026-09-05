import os
import time

import pytest

from app.auth import get_actor
from app.config import Settings
from app.contracts import DocumentACL
from app.db import engine_for, migrate
from app.knowledge import Knowledge
from app.services import seed

pytestmark = pytest.mark.integration


@pytest.fixture
def real(tmp_path):
    url = os.environ.get("AI_OFFICE_TEST_QDRANT_URL")
    if not url:
        pytest.skip("Run make integration-test to provision real Qdrant")
    settings = Settings(data_dir=tmp_path / "data", qdrant_url=url, _env_file=None)
    migrate(settings)
    migrate(settings)
    engine = engine_for(settings)
    k = Knowledge(engine, settings)
    seed(engine, settings, k, time.time())
    with engine.connect() as conn:
        owner = get_actor(conn, "owner")
        employee = get_actor(conn, "employee")
    yield k, owner, employee, settings
    k.client.close()
    engine.dispose()


def test_canary_real_server_reconnect_and_acl(real):
    k, owner, employee, s = real
    evidence = k.search(employee, "лимит самостоятельного согласования закупок")
    assert evidence and any("100 000" in e["fragment"] for e in evidence)
    collection = k.index_name
    reconnect = Knowledge(k.engine, s)
    assert reconnect.search(employee, "лимит закупок")
    assert reconnect.index_name == collection
    private = k.import_document(
        owner, "private.md", b"Rare zircon procurement price hidden", ["owner"], "integration"
    )
    assert all(
        e["source_id"] != private["document_id"]
        for e in reconnect.search(employee, "Rare zircon procurement price")
    )
    reconnect.client.close()


def test_real_version_revoke_and_partial_index_exclusion(real, monkeypatch):
    k, owner, employee, _ = real
    first = k.import_document(
        owner, "rules.txt", b"Orchid threshold 700 RUB.", ["owner", "employee"], "integration"
    )
    k.import_document(
        owner, "rules.txt", b"Orchid threshold 900 RUB.", ["owner", "employee"], "integration"
    )
    found = [
        e for e in k.search(employee, "Orchid threshold") if e["source_id"] == first["document_id"]
    ]
    assert found and all(e["version"] == 2 for e in found)
    original = k.store.add_documents

    def partial(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Failure after Qdrant upsert but before SQL publication")

    monkeypatch.setattr(k.store, "add_documents", partial)
    from app.errors import DomainError

    with pytest.raises(DomainError):
        k.import_document(
            owner, "rules.txt", b"Orchid threshold 1200 RUB.", ["owner", "employee"], "integration"
        )
    assert all(
        e["version"] == 2
        for e in k.search(employee, "Orchid threshold")
        if e["source_id"] == first["document_id"]
    )
    k.update_acl(
        owner, first["document_id"], DocumentACL(roles=["owner"], revoked=True), "integration"
    )
    assert all(
        e["source_id"] != first["document_id"] for e in k.search(employee, "Orchid threshold")
    )


def test_embedding_change_creates_new_collection_without_reset(real, monkeypatch):
    import app.knowledge as module
    from app.providers import DemoEmbeddings

    k, owner, employee, s = real
    old = k.ensure_store().collection_name

    class Different(DemoEmbeddings):
        dimensions = 256

    monkeypatch.setattr(module, "embeddings_for", lambda _: (Different(), "different-model-v2"))
    newer = Knowledge(k.engine, s)
    newer.ensure_store()
    assert newer.index_name != old
    assert newer.client.collection_exists(old)
    assert newer.search(employee, "procurement") == []
    newer.client.close()
