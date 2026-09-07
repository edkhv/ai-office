import io
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from app.auth import authenticate, get_actor
from app.backup import (
    MAGIC,
    _open,
    _seal,
    create_backup,
    data_lease,
    read_passphrase,
    restore_backup,
)
from app.config import Settings
from app.db import engine_for, migrate
from app.errors import DomainError
from app.knowledge import Knowledge
from app.services import seed

PASSWORD = "a unique long test passphrase"


@pytest.fixture
def offline(tmp_path):
    settings = Settings(data_dir=tmp_path / "source", _env_file=None)
    migrate(settings)
    engine = engine_for(settings)
    client = QdrantClient(":memory:")
    knowledge = Knowledge(engine, settings, client=client)
    seed(engine, settings, knowledge, 1788760800)
    with engine.connect() as conn:
        owner = get_actor(conn, "owner")
    yield settings, engine, knowledge, owner
    client.close()
    engine.dispose()


def restore_settings(tmp_path):
    return Settings(data_dir=tmp_path / "restored", _env_file=None)


def archive_for(offline, tmp_path):
    archive = tmp_path / "backup.aioffice"
    create_backup(offline[0], archive, PASSWORD)
    return archive


def test_backup_roundtrip_revokes_tokens_preserves_sources_and_versions(offline, tmp_path):
    settings, engine, knowledge, owner = offline
    first = knowledge.import_document(
        owner, "policy.txt", b"Policy: offer expires in 25 days.", ["owner"], "test"
    )
    knowledge.import_document(
        owner,
        "policy.txt",
        b"Policy: offer expires in 30 days.",
        ["owner"],
        "test",
        first["document_id"],
    )
    prior_token = (settings.data_dir / "owner.token").read_text().strip()
    archive = archive_for(offline, tmp_path)
    assert archive.read_bytes().startswith(MAGIC)
    assert b"offer expires" not in archive.read_bytes()
    assert stat.S_IMODE(archive.stat().st_mode) == 0o600
    target = restore_settings(tmp_path)
    qdrant = QdrantClient(":memory:")
    result = restore_backup(target, archive, PASSWORD, qdrant)
    assert result["previous_credentials_revoked"]
    restored_engine = engine_for(target)
    restored = Knowledge(restored_engine, target, client=qdrant)
    assert restored.get_document(owner, first["document_id"], 1)["source"]["version"] == 1
    assert restored.get_document(owner, first["document_id"])["current_version"] == 2
    hits = restored.search(owner, "offer expires")
    assert hits
    with pytest.raises(DomainError):
        authenticate(restored_engine, prior_token, 1788760800)
    token = (target.data_dir / "recovery-owner.token").read_text().strip()
    assert authenticate(restored_engine, token, 1788760800).id == owner.id
    assert not (target.data_dir / "owner.token").exists()
    with sqlite3.connect(target.data_dir / "office.db") as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM credentials WHERE revoked=0").fetchone()[0] == 1
    qdrant.close()
    restored_engine.dispose()


@pytest.mark.parametrize("damage", ["wrong-password", "tamper", "truncate"])
def test_authentication_failure_publishes_nothing(offline, tmp_path, damage):
    archive = archive_for(offline, tmp_path)
    password = PASSWORD
    if damage == "wrong-password":
        password = "another sufficiently long passphrase"
    elif damage == "tamper":
        blob = bytearray(archive.read_bytes())
        blob[-8] ^= 1
        archive.write_bytes(blob)
    else:
        archive.write_bytes(archive.read_bytes()[:40])
    target = restore_settings(tmp_path)
    with pytest.raises(ValueError):
        restore_backup(target, archive, password)
    assert {p.name for p in target.data_dir.iterdir()} == {".maintenance.lock"}


def test_running_runtime_refuses_backup_and_restore(offline, tmp_path):
    settings = offline[0]
    with data_lease(settings):
        with pytest.raises(RuntimeError, match="in use"):
            create_backup(settings, tmp_path / "refused", PASSWORD)
    target = restore_settings(tmp_path)
    with data_lease(target):
        with pytest.raises(RuntimeError, match="in use"):
            restore_backup(target, tmp_path / "nonexistent", PASSWORD)
    with data_lease(settings, exclusive=True):
        with pytest.raises(RuntimeError, match="in use"):
            with data_lease(settings):
                pass


def test_restore_refuses_nonempty_target(offline, tmp_path):
    target = restore_settings(tmp_path)
    target.data_dir.mkdir()
    (target.data_dir / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="empty new"):
        restore_backup(target, archive_for(offline, tmp_path), PASSWORD)
    assert (target.data_dir / "keep.txt").read_text() == "keep"


@pytest.mark.parametrize(
    "attack", ["traversal", "symlink", "duplicate", "compressed", "missing", "hash"]
)
def test_untrusted_archive_inventory_rejected(offline, tmp_path, attack):
    archive = archive_for(offline, tmp_path)
    payload = _open(archive.read_bytes(), PASSWORD)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        entries = {n: z.read(n) for n in z.namelist()}
    buffer = io.BytesIO()
    if attack == "missing":
        del entries[next(n for n in entries if n.startswith("documents/"))]
    elif attack == "hash":
        entries["office.db"] += b"wrong"
    with zipfile.ZipFile(buffer, "w") as z:
        for name, content in entries.items():
            z.writestr(
                name,
                content,
                compress_type=zipfile.ZIP_DEFLATED
                if attack == "compressed"
                else zipfile.ZIP_STORED,
            )
        if attack == "traversal":
            z.writestr("../escape", b"bad")
        elif attack == "duplicate":
            with pytest.warns(UserWarning):
                z.writestr("office.db", entries["office.db"])
        elif attack == "symlink":
            item = zipfile.ZipInfo("documents/11111111-1111-1111-1111-111111111111-1.txt")
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(item, b"/etc/passwd")
    archive.write_bytes(_seal(buffer.getvalue(), PASSWORD))
    target = restore_settings(tmp_path)
    with pytest.raises(ValueError):
        restore_backup(target, archive, PASSWORD)
    assert not (target.data_dir / "office.db").exists()
    assert not (tmp_path / "escape").exists()


def test_missing_or_tampered_source_refuses_backup(offline, tmp_path):
    source = next((offline[0].data_dir / "documents").glob("*.txt"))
    source.write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        create_backup(offline[0], tmp_path / "invalid", PASSWORD)
    assert not (tmp_path / "invalid").exists()
    source.unlink()
    with pytest.raises(FileNotFoundError):
        create_backup(offline[0], tmp_path / "missing", PASSWORD)


def test_private_passphrase_file_and_archive_no_overwrite(offline, tmp_path):
    key = tmp_path / "key"
    key.write_text(PASSWORD)
    key.chmod(0o600)
    assert read_passphrase(key) == PASSWORD
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        read_passphrase(key)
    key.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(key)
    with pytest.raises((ValueError, OSError)):
        read_passphrase(link)
    archive = archive_for(offline, tmp_path)
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        create_backup(offline[0], archive, PASSWORD)
    assert archive.read_bytes() == original


def test_populated_qdrant_is_preserved(offline, tmp_path):
    archive = archive_for(offline, tmp_path)
    client = offline[2].client
    before = client.count(offline[2].index_name).count
    target = restore_settings(tmp_path)
    with pytest.raises(ValueError, match="fresh Qdrant"):
        restore_backup(target, archive, PASSWORD, client)
    assert client.count(offline[2].index_name).count == before
    assert not (target.data_dir / "office.db").exists()


def test_failed_reindex_has_no_destination_and_can_retry(offline, tmp_path, monkeypatch):
    archive = archive_for(offline, tmp_path)
    target = restore_settings(tmp_path)
    client = QdrantClient(":memory:")
    from app import backup

    original = backup.rebuild_current_sources

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("simulated index failure")

    monkeypatch.setattr(backup, "rebuild_current_sources", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        restore_backup(target, archive, PASSWORD, client)
    assert {p.name for p in target.data_dir.iterdir()} == {".maintenance.lock"}
    monkeypatch.setattr(backup, "rebuild_current_sources", original)
    assert restore_backup(target, archive, PASSWORD, client)["restored"]
    client.close()


def test_company_docx_pdf_quote_task_restore(tmp_path):
    from docx import Document as WordDocument
    from pypdf import PdfReader
    from sqlalchemy import select

    from app import workspace
    from app.contracts import Decision
    from app.providers import DemoProvider
    from app.quote_contracts import QuoteDraft
    from app.quotes import Quotes
    from app.schema_v1 import tasks
    from app.workflows import Workflows
    from app.workspace_contracts import Setup, UserCreate

    now = 1788760800
    settings = Settings(data_mode="pilot", data_dir=tmp_path / "company", _env_file=None)
    migrate(settings)
    engine = engine_for(settings)
    workspace.initialize(engine, settings, now)
    setup = workspace.complete_setup(
        engine,
        settings,
        Setup(
            token=(settings.data_dir / "setup.token").read_text().strip(),
            company_name="Example Customer",
            owner_display_name="Director",
        ),
        now,
        "test",
    )
    with engine.connect() as conn:
        owner = get_actor(conn, setup["user"]["id"])
    employee = workspace.create_user(
        engine,
        settings,
        owner,
        UserCreate(display_name="Sales", role="employee", team_id="procurement"),
        now,
        "test",
    )
    client = QdrantClient(":memory:")
    knowledge = Knowledge(engine, settings, client=client, clock=lambda: now)
    word = WordDocument()
    word.add_paragraph("Delivery of steel is required in 30 days.")
    content = io.BytesIO()
    word.save(content)
    source = knowledge.import_document(
        owner, "request.docx", content.getvalue(), ["owner", "employee"], "test"
    )
    quotes = Quotes(engine, settings, knowledge, lambda: now)
    catalog = quotes.import_catalog(
        owner, "prices.csv", Path("examples/catalogs/synthetic-demo.csv").read_bytes(), "test"
    )
    draft = QuoteDraft.model_validate(
        {
            "title": "Company quotation",
            "customer": "Customer One",
            "catalog_version_id": catalog["id"],
            "source_document_id": source["document_id"],
            "source_document_version": 1,
            "lines": [{"sku": "STEEL-01", "quantity": "3"}],
            "task": {
                "title": "Deliver quote",
                "team_id": "procurement",
                "assignee_id": employee["user"]["id"],
                "due_at": "2026-09-11T15:00:00+03:00",
                "acceptance_criteria": "Quote reviewed",
            },
        }
    )
    quote = quotes.save(owner, draft, "test")
    proposed = quotes.propose(owner, quote["id"], 1, "quote-submit", "test")
    work = Workflows(engine, settings, DemoProvider(), knowledge, lambda: now)
    work.decide(
        owner,
        proposed["proposal"]["id"],
        Decision(decision="approve", version=1, payload_hash=proposed["proposal"]["payload_hash"]),
    )
    assert work.process_one()
    pdf = quotes.export(owner, quote["id"], "pdf")
    pdf_source = knowledge.import_document(owner, "approved.pdf", pdf, ["owner"], "test")
    archive = tmp_path / "company.aioffice"
    create_backup(settings, archive, PASSWORD)
    target = settings.model_copy(update={"data_dir": tmp_path / "restored-company"})
    fresh = QdrantClient(":memory:")
    result = restore_backup(target, archive, PASSWORD, fresh)
    assert result["recovery_actor_id"] == owner.id
    restored_engine = engine_for(target)
    restored = Knowledge(restored_engine, target, client=fresh)
    with restored_engine.connect() as conn:
        assert workspace.profile(conn)["company_name"] == "Example Customer"
        assert workspace.profile(conn)["setup_completed"]
        assigned = conn.execute(select(tasks)).mappings().all()
        assert len(assigned) == 1
    assert len(workspace.list_users(restored_engine, owner)) == 2
    assert (
        restored.original_document(owner, source["document_id"], 1)["content"] == content.getvalue()
    )
    assert restored.original_document(owner, pdf_source["document_id"], 1)["content"] == pdf
    result_quote = Quotes(restored_engine, target, restored).get(owner, quote["id"])
    assert result_quote["revision"]["status"] == "approved"
    exported = Quotes(restored_engine, target, restored).export(owner, quote["id"], "pdf")
    assert "Customer One" in "\n".join(
        p.extract_text() for p in PdfReader(io.BytesIO(exported)).pages
    )
    assert restored.search(owner, "steel delivery")
    client.close()
    fresh.close()
    engine.dispose()
    restored_engine.dispose()


def test_unfinished_company_setup_refuses_backup(tmp_path):
    from app.workspace import initialize

    settings = Settings(data_mode="pilot", data_dir=tmp_path / "unfinished", _env_file=None)
    migrate(settings)
    engine = engine_for(settings)
    initialize(engine, settings, 1788760800)
    with pytest.raises(ValueError, match="Complete workspace setup"):
        create_backup(settings, tmp_path / "unfinished.aioffice", PASSWORD)
    assert not (tmp_path / "unfinished.aioffice").exists()
    engine.dispose()


def test_restore_data_mode_mismatch(offline, tmp_path):
    target = Settings(data_mode="pilot", data_dir=tmp_path / "wrong-mode", _env_file=None)
    with pytest.raises(ValueError, match="same data mode"):
        restore_backup(target, archive_for(offline, tmp_path), PASSWORD)
    assert {p.name for p in target.data_dir.iterdir()} == {".maintenance.lock"}


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_linked_source_is_rejected(offline, tmp_path, kind):
    import os

    source = next((offline[0].data_dir / "documents").glob("*.txt"))
    copy = tmp_path / "outside-source"
    source.rename(copy)
    if kind == "symlink":
        source.symlink_to(copy)
    else:
        os.link(copy, source)
    with pytest.raises((ValueError, OSError)):
        create_backup(offline[0], tmp_path / "unsafe.aioffice", PASSWORD)
    assert not (tmp_path / "unsafe.aioffice").exists()


def test_failed_publish_cleans_owned_index_for_retry(offline, tmp_path, monkeypatch):
    from app import backup

    archive = archive_for(offline, tmp_path)
    target = restore_settings(tmp_path)
    client = QdrantClient(":memory:")
    original = backup.os.rename

    def fail_database(source, destination):
        if source.name == "office.db":
            raise OSError("simulated publish failure")
        return original(source, destination)

    monkeypatch.setattr(backup.os, "rename", fail_database)
    with pytest.raises(OSError, match="simulated"):
        restore_backup(target, archive, PASSWORD, client)
    assert {p.name for p in target.data_dir.iterdir()} == {".maintenance.lock"}
    assert not client.get_collections().collections
    monkeypatch.setattr(backup.os, "rename", original)
    assert restore_backup(target, archive, PASSWORD, client)["restored"]
    client.close()


def test_existing_empty_qdrant_collection_is_not_owned_or_modified(offline, tmp_path):
    from qdrant_client import models

    archive = archive_for(offline, tmp_path)
    client = QdrantClient(":memory:")
    index_name = offline[2].index_name
    client.create_collection(
        index_name, vectors_config=models.VectorParams(size=512, distance=models.Distance.COSINE)
    )
    target = restore_settings(tmp_path)
    with pytest.raises(ValueError, match="fresh Qdrant"):
        restore_backup(target, archive, PASSWORD, client)
    assert client.collection_exists(index_name)
    assert client.count(index_name, exact=True).count == 0
    assert {p.name for p in target.data_dir.iterdir()} == {".maintenance.lock"}
    client.close()
