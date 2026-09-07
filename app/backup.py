"""Offline, authenticated pilot backups. No credentials are printed or restored as valid."""

import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from sqlalchemy import select

from app.auth import issue_credential, write_private
from app.db import engine_for, rows, transaction
from app.document_schema import sources
from app.knowledge import Knowledge
from app.schema_v1 import documents, versions

MAGIC = b"AI-OFFICE-BACKUP-1\x00"
MAX_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 10000
SOURCE_NAME = re.compile(r"[a-f0-9-]{36}-\d+(?:\.original\.(?:txt|md|pdf|docx)|\.txt)")


class BackupError(ValueError):
    """A fixed, public diagnostic that cannot include archive or environment contents."""


class DataLeaseError(RuntimeError):
    """A fixed runtime maintenance diagnostic."""


@contextmanager
def data_lease(settings, exclusive=False):
    """All runtime writers hold shared leases; offline maintenance requires exclusive access."""
    directory = settings.data_dir
    if directory.is_symlink():
        raise DataLeaseError("Unsafe data directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / ".maintenance.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DataLeaseError(
                "Data directory is in use; stop app, worker and CLI writers"
            ) from None
        yield
    finally:
        os.close(fd)


def _read(path, limit=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise BackupError("Unsafe or oversized backup input")
        content = stream.read(limit + 1)
        if len(content) > limit:
            raise BackupError("Backup size limit exceeded")
        return content


def read_passphrase(path):
    path = Path(path)
    info = path.lstat()
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise BackupError("Passphrase file must be private (chmod 600)")
    value = _read(path, 4096).decode("utf-8").rstrip("\r\n")
    _password(value)
    return value


def _password(value):
    if not isinstance(value, str) or len(value) < 16 or len(value.encode()) > 4096:
        raise BackupError("Use a passphrase of 16 to 4096 bytes")


def _key(password, salt):
    _password(password)
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def _seal(payload, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    return header + AESGCM(_key(password, salt)).encrypt(nonce, payload, header)


def _open(payload, password):
    if not payload.startswith(MAGIC) or len(payload) < len(MAGIC) + 44:
        raise BackupError("Unsupported or damaged backup")
    offset = len(MAGIC)
    header = payload[: offset + 28]
    try:
        return AESGCM(_key(password, payload[offset : offset + 16])).decrypt(
            payload[offset + 16 : offset + 28], payload[offset + 28 :], header
        )
    except InvalidTag:
        raise BackupError("Wrong passphrase or damaged backup") from None


def _references(database):
    """Every immutable version, including historical citations and revoked sources."""
    with sqlite3.connect(database) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BackupError("Database integrity check failed")
        refs = dict(conn.execute("SELECT file_name, content_hash FROM document_versions"))
        refs.update(conn.execute("SELECT original_file_name, original_hash FROM document_sources"))
    for name in refs:
        if not isinstance(name, str) or not SOURCE_NAME.fullmatch(name):
            raise BackupError("Unsafe document storage reference")
    return refs


def create_backup(settings, output, password):
    """Stop runtime processes first. Never copy raw token files or Qdrant storage."""
    _password(password)
    output = Path(output)
    with data_lease(settings, exclusive=True):
        source = settings.data_dir / "office.db"
        _read(source)  # Reject symlinks, hardlinks and oversize before SQLite follows a path.
        directory = settings.data_dir / "documents"
        if directory.is_symlink():
            raise BackupError("Unsafe document directory")
        with tempfile.TemporaryDirectory(prefix=".backup-", dir=settings.data_dir) as temporary:
            os.chmod(temporary, 0o700)
            database = Path(temporary) / "office.db"
            with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as origin:
                with sqlite3.connect(database) as target:
                    origin.backup(target)
            os.chmod(database, 0o600)
            with sqlite3.connect(database) as check:
                profile = check.execute(
                    "SELECT data_mode, setup_completed FROM workspace_profiles WHERE id='workspace'"
                ).fetchone()
                if not profile or not profile[1]:
                    raise BackupError("Complete workspace setup before creating a backup")
                if profile[0] != getattr(settings, "data_mode", "demo"):
                    raise BackupError("Configured data mode does not match this workspace")
                if not check.execute(
                    "SELECT id FROM actors WHERE active=1 AND role='owner' LIMIT 1"
                ).fetchone():
                    raise BackupError("Workspace requires an active owner for recovery")
            entries = {"office.db": _read(database)}
            for name, expected in _references(database).items():
                content = _read(directory / name, 32 * 1024 * 1024)
                if hashlib.sha256(content).hexdigest() != expected:
                    raise BackupError("Document hash mismatch")
                entries["documents/" + name] = content
                if sum(map(len, entries.values())) > MAX_BYTES:
                    raise BackupError("Pilot backup exceeds 256 MiB")
            if len(entries) > MAX_ENTRIES:
                raise BackupError("Too many backup entries")
            manifest = {
                "format": 1,
                "created_at": time.time(),
                "settings": {
                    "data_mode": getattr(settings, "data_mode", "demo"),
                    "org_timezone": settings.org_timezone,
                    "mode": settings.mode,
                    "embedding_provider": settings.embedding_provider,
                },
                "files": {
                    name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                    for name, content in entries.items()
                },
            }
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
                archive.writestr("manifest.json", json.dumps(manifest).encode())
            blob = _seal(buffer.getvalue(), password)
            if len(blob) > MAX_BYTES:
                raise BackupError("Pilot backup exceeds 256 MiB including archive overhead")
            fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(blob)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                output.unlink(missing_ok=True)
                raise
    return {"format": 1, "files": len(entries), "bytes": len(blob), "encrypted": True}


def _unpack(payload, staging):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if (
            len(infos) > MAX_ENTRIES + 1
            or len(set(names)) != len(names)
            or "manifest.json" not in names
            or "office.db" not in names
            or sum(item.file_size for item in infos) > MAX_BYTES
        ):
            raise BackupError("Invalid backup inventory")
        for item in infos:
            name = item.filename
            mode = item.external_attr >> 16
            if (
                item.compress_type != zipfile.ZIP_STORED
                or item.flag_bits & 1
                or item.file_size < 0
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                or not (
                    name in {"office.db", "manifest.json"}
                    or (name.startswith("documents/") and SOURCE_NAME.fullmatch(name[10:]))
                )
            ):
                raise BackupError("Unsafe backup entry")
        if archive.getinfo("manifest.json").file_size > 4 * 1024 * 1024:
            raise BackupError("Oversized manifest")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != 1 or set(manifest.get("files", {})) != set(names) - {
            "manifest.json"
        }:
            raise BackupError("Invalid backup manifest")
        for name, expected in manifest["files"].items():
            content = archive.read(name)
            if (
                len(content) != expected["size"]
                or hashlib.sha256(content).hexdigest() != expected["sha256"]
            ):
                raise BackupError("Backup entry hash mismatch")
            target = staging / name
            target.parent.mkdir(exist_ok=True, mode=0o700)
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for name, expected in _references(staging / "office.db").items():
            content = _read(staging / "documents" / name, 32 * 1024 * 1024)
            if hashlib.sha256(content).hexdigest() != expected:
                raise BackupError("Missing or inconsistent immutable source")
        return manifest


def rebuild_current_sources(engine, settings, client=None):
    """Upsert current versions without regenerating IDs, versions or source metadata."""
    knowledge = Knowledge(engine, settings, client=client)
    store = knowledge.ensure_store()
    with engine.connect() as conn:
        docs = rows(conn, select(documents).where(documents.c.revoked.is_(False)))
    count = 0
    for doc in docs:
        if not doc["current_version"]:
            continue
        with engine.connect() as conn:
            version = (
                conn.execute(
                    select(versions).where(
                        versions.c.document_id == doc["id"],
                        versions.c.version == doc["current_version"],
                    )
                )
                .mappings()
                .one()
            )
            metadata = (
                conn.execute(select(sources).where(sources.c.version_id == version["id"]))
                .mappings()
                .first()
            )
        text = knowledge.read_source(version["file_name"])
        parts = knowledge.anchored_chunks(text, metadata["anchors"] if metadata else [])
        records = [
            Document(
                page_content=part,
                metadata={
                    "organization_id": doc["organization_id"],
                    "document_id": doc["id"],
                    "version_id": version["id"],
                    "version": version["version"],
                    "content_hash": version["content_hash"],
                    "start": start,
                    "end": end,
                    "observed_at": version["observed_at"],
                    "fragment_ref": ref,
                },
            )
            for start, end, part, ref in parts
        ]
        ids = [
            str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{doc['organization_id']}/{doc['id']}/{version['version']}/{i}",
                )
            )
            for i in range(len(parts))
        ]
        store.add_documents(records, ids=ids)
        with transaction(engine) as conn:
            conn.execute(
                versions.update()
                .where(versions.c.id == version["id"])
                .values(state="indexed", index_name=knowledge.index_name)
            )
        count += 1
    return count


def restore_backup(settings, archive_path, password, client=None):
    """Require an empty target and a fresh collection-free Qdrant; publish DB last."""
    with data_lease(settings, exclusive=True):
        if any(p.name != ".maintenance.lock" for p in settings.data_dir.iterdir()):
            raise BackupError("Restore requires an empty new data directory")
        payload = _open(_read(Path(archive_path)), password)
        published = []
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=settings.data_dir) as temporary:
            staging = Path(temporary)
            os.chmod(staging, 0o700)
            manifest = _unpack(payload, staging)
            if manifest["settings"]["data_mode"] != getattr(settings, "data_mode", "demo"):
                raise BackupError("Configure the same data mode as the backup before restoring")
            staged_settings = settings.model_copy(update={"data_dir": staging})
            with sqlite3.connect(staging / "office.db") as conn:
                conn.execute("UPDATE credentials SET revoked = 1")
                conn.execute("DELETE FROM sessions")
                conn.execute("DELETE FROM login_limits")
                conn.execute("DELETE FROM heartbeats")
                owner = conn.execute(
                    "SELECT id FROM actors WHERE active = 1 AND role = 'owner' ORDER BY id LIMIT 1"
                ).fetchone()
                if not owner:
                    raise BackupError("Backup has no active owner for recovery")
            engine = engine_for(staged_settings)
            empty_collection = False
            owned_collection = False
            probe = None
            try:
                # Dedicated recovery service: even empty existing collections are not ours.
                vector_client = client or QdrantClient(
                    url=staged_settings.check_url(staged_settings.qdrant_url),
                    timeout=5,
                    check_compatibility=False,
                    trust_env=False,
                )
                existing_names = {item.name for item in vector_client.get_collections().collections}
                if existing_names:
                    raise BackupError("Restore requires a fresh Qdrant service with no collections")
                probe = Knowledge(engine, staged_settings, client=vector_client)
                probe.ensure_store()
                owned_collection = probe.index_name not in existing_names
                if probe.client.count(probe.index_name, exact=True).count:
                    raise BackupError("Restore requires a fresh Qdrant service with no collections")
                empty_collection = True
                indexed = rebuild_current_sources(engine, staged_settings, probe.client)
                token = issue_credential(engine, staged_settings, owner[0], time.time())
                write_private(staging / "recovery-owner.token", token + "\n")
                with engine.connect() as conn:
                    conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            except BaseException:
                # This dedicated collection was verified empty before indexing.
                if probe is not None and probe.client is not None and probe.index_name:
                    # Existing nonempty collections must never be removed on failed preflight.
                    if empty_collection and owned_collection:
                        probe.client.delete_collection(probe.index_name)
                raise
            finally:
                engine.dispose()
            try:
                for name in ("documents", "recovery-owner.token", "office.db"):
                    source = staging / name
                    if source.exists():
                        target = settings.data_dir / name
                        os.rename(source, target)
                        published.append(target)
            except BaseException:
                if owned_collection:
                    probe.client.delete_collection(probe.index_name)
                for target in reversed(published):
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
                raise
    return {
        "restored": True,
        "indexed_documents": indexed,
        "recovery_actor_id": owner[0],
        "recovery_token_file": str(settings.data_dir / "recovery-owner.token"),
        "previous_credentials_revoked": True,
    }


def main():
    import argparse
    import getpass

    from app.config import Settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["backup", "restore"])
    parser.add_argument("archive", type=Path)
    parser.add_argument("--passphrase-file", type=Path)
    args = parser.parse_args()
    try:
        password = (
            read_passphrase(args.passphrase_file)
            if args.passphrase_file
            else getpass.getpass("Backup passphrase (at least 16 characters): ")
        )
        if args.command == "backup" and not args.passphrase_file:
            if password != getpass.getpass("Repeat passphrase: "):
                raise BackupError("Passphrases do not match")
        action = create_backup if args.command == "backup" else restore_backup
        result = action(Settings(), args.archive, password)
    except Exception as exc:
        # No archive content, model URL, business records or secret is logged.
        safe = str(exc) if isinstance(exc, (BackupError, DataLeaseError)) else type(exc).__name__
        raise SystemExit("Backup operation failed: " + safe) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
