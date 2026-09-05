import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models
from sqlalchemy import select

from app.auth import require
from app.db import digest, record, row, rows, transaction, uid
from app.errors import DomainError
from app.providers import embeddings_for
from app.schema_v1 import documents, versions


def chunks(text, size=700, overlap=80):
    text = text.replace("\r\n", "\n").strip()
    result, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        result.append((start, end, text[start:end]))
        if end == len(text):
            break
        start = end - overlap
    return result


class Knowledge:
    def __init__(self, engine, settings, client=None, clock=time.time):
        self.engine, self.settings, self.clock = engine, settings, clock
        self.client = client
        self.store = None
        self.index_name = None

    def ensure_store(self):
        if self.store:
            return self.store
        embedding, spec = embeddings_for(self.settings)
        try:
            size = len(embedding.embed_query("index dimension probe"))
            self.index_name = (
                "office_" + digest({"embedding": spec, "size": size, "chunk": "v1"})[:20]
            )
            if self.client is None:
                self.client = QdrantClient(
                    url=self.settings.check_url(self.settings.qdrant_url),
                    timeout=5,
                    check_compatibility=False,
                    trust_env=False,
                )
            if not self.client.collection_exists(self.index_name):
                self.client.create_collection(
                    self.index_name,
                    vectors_config=models.VectorParams(size=size, distance=models.Distance.COSINE),
                )
            self.store = QdrantVectorStore(
                client=self.client,
                collection_name=self.index_name,
                embedding=embedding,
                validate_embeddings=False,
                validate_collection_config=True,
            )
            return self.store
        except Exception as exc:
            raise DomainError("RETRIEVAL_UNAVAILABLE", 503, retryable=True) from exc

    def source_path(self, file_name):
        if not re.fullmatch(r"[a-f0-9-]{36}-\d+\.txt", file_name):
            raise DomainError("INVALID_STORAGE_ID", 400)
        root = self.settings.data_dir.resolve()
        directory = root / "documents"
        if directory.is_symlink():
            raise DomainError("UNSAFE_STORAGE", 400)
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / file_name
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise DomainError("UNSAFE_STORAGE", 400)
        return path

    def read_source(self, file_name):
        path = self.source_path(file_name)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, encoding="utf-8") as stream:
            return stream.read()

    def import_document(
        self,
        actor,
        filename,
        content,
        roles,
        correlation_id,
        document_id=None,
        content_type="text/plain",
        observed_at=None,
    ):
        require(actor, "owner", "manager")
        if not roles or not set(roles) <= {"owner", "manager", "employee"}:
            raise DomainError("INVALID_ACL", 422)
        if actor.role == "manager" and "manager" not in roles:
            raise DomainError("FORBIDDEN", 403)
        if len(content) > self.settings.max_upload_bytes:
            raise DomainError("UPLOAD_TOO_LARGE", 413)
        if (
            len(filename) > 200
            or "/" in filename
            or "\\" in filename
            or Path(filename).suffix.lower() not in {".md", ".txt"}
            or content_type not in {"text/plain", "text/markdown", "application/octet-stream"}
        ):
            raise DomainError("UNSUPPORTED_DOCUMENT", 415)
        try:
            text = content.decode("utf-8").replace("\r\n", "\n").strip()
        except UnicodeError as exc:
            raise DomainError("INVALID_UTF8", 422) from exc
        if not text or "\x00" in text:
            raise DomainError("EMPTY_OR_BINARY_DOCUMENT", 422)
        hashed = digest(text)
        now = self.clock()
        observed_at = observed_at or datetime.fromtimestamp(now, UTC).isoformat()
        with transaction(self.engine) as conn:
            doc = self.get_document(actor, document_id, conn=conn) if document_id else None
            if not doc:
                # Same name/content in a visible document is idempotent, not a global hash oracle.
                candidates = rows(
                    conn,
                    select(documents).where(
                        documents.c.organization_id == actor.organization_id,
                        documents.c.name == filename,
                        documents.c.revoked.is_(False),
                    ),
                )
                doc = next((d for d in candidates if actor.role in d["roles"]), None)
            if doc:
                document_id = doc["id"]
                existing = row(
                    conn,
                    select(versions)
                    .where(versions.c.document_id == document_id, versions.c.content_hash == hashed)
                    .order_by(versions.c.version.desc()),
                )
                if (
                    existing
                    and existing["state"] == "indexed"
                    and existing["version"] == doc["current_version"]
                ):
                    return {
                        "document_id": document_id,
                        "version": existing["version"],
                        "state": "indexed",
                        "replayed": True,
                    }
                if existing and existing["state"] in {"pending", "failed"}:
                    version_row = existing
                    conn.execute(
                        versions.update()
                        .where(versions.c.id == existing["id"])
                        .values(state="pending")
                    )
                else:
                    prior = rows(
                        conn, select(versions).where(versions.c.document_id == document_id)
                    )
                    version_row = self.new_version(
                        conn,
                        document_id,
                        max((v["version"] for v in prior), default=0) + 1,
                        hashed,
                        observed_at,
                    )
            else:
                document_id = uid()
                conn.execute(
                    documents.insert().values(
                        id=document_id,
                        organization_id=actor.organization_id,
                        name=filename,
                        roles=sorted(set(roles)),
                        revoked=False,
                        current_version=0,
                    )
                )
                version_row = self.new_version(conn, document_id, 1, hashed, observed_at)
        try:
            path = self.source_path(version_row["file_name"])
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                if digest(self.read_source(version_row["file_name"])) != hashed:
                    raise DomainError("SOURCE_HASH_MISMATCH", 409) from None
            store = self.ensure_store()
            parts = chunks(text)
            docs = [
                Document(
                    page_content=part,
                    metadata={
                        "organization_id": actor.organization_id,
                        "document_id": document_id,
                        "version_id": version_row["id"],
                        "version": version_row["version"],
                        "content_hash": hashed,
                        "start": start,
                        "end": end,
                        "observed_at": observed_at,
                    },
                )
                for start, end, part in parts
            ]
            ids = [
                str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{actor.organization_id}/{document_id}/{version_row['version']}/{i}",
                    )
                )
                for i in range(len(parts))
            ]
            store.add_documents(docs, ids=ids)
            with transaction(self.engine) as conn:
                current = row(conn, select(documents).where(documents.c.id == document_id))
                if current["revoked"] or actor.role not in current["roles"]:
                    raise DomainError("FORBIDDEN", 403)
                conn.execute(
                    versions.update()
                    .where(versions.c.id == version_row["id"])
                    .values(state="indexed", index_name=self.index_name)
                )
                # An older slow import must not supersede a newer published version.
                if current["current_version"] < version_row["version"]:
                    conn.execute(
                        documents.update()
                        .where(documents.c.id == document_id)
                        .values(current_version=version_row["version"])
                    )
                record(
                    conn,
                    actor,
                    "document_import",
                    document_id,
                    "succeeded",
                    correlation_id,
                    {"version": version_row["version"], "hash": hashed},
                    now=now,
                )
        except Exception as exc:
            with transaction(self.engine) as conn:
                conn.execute(
                    versions.update()
                    .where(versions.c.id == version_row["id"])
                    .values(state="failed")
                )
                record(
                    conn,
                    actor,
                    "document_import",
                    document_id,
                    "failed",
                    correlation_id,
                    {"version": version_row["version"]},
                    now=now,
                )
            if isinstance(exc, DomainError):
                raise
            raise DomainError("INDEXING_FAILED", 503, retryable=True) from exc
        return {
            "document_id": document_id,
            "version": version_row["version"],
            "state": "indexed",
            "replayed": False,
        }

    def new_version(self, conn, document_id, version, hashed, observed_at):
        values = dict(
            id=uid(),
            document_id=document_id,
            version=version,
            content_hash=hashed,
            state="pending",
            file_name=f"{document_id}-{version}.txt",
            observed_at=observed_at,
        )
        conn.execute(versions.insert().values(**values))
        return values

    def get_document(self, actor, document_id, version=None, conn=None):
        if conn is None:
            with self.engine.connect() as connection:
                return self.get_document(actor, document_id, version, connection)
        doc = row(
            conn,
            select(documents).where(
                documents.c.id == document_id,
                documents.c.organization_id == actor.organization_id,
                documents.c.revoked.is_(False),
            ),
        )
        if not doc or actor.role not in doc["roles"]:
            raise DomainError("NOT_FOUND", 404)
        if version is not None:
            source = row(
                conn,
                select(versions).where(
                    versions.c.document_id == document_id,
                    versions.c.version == version,
                    versions.c.state == "indexed",
                ),
            )
            if not source:
                raise DomainError("NOT_FOUND", 404)
            doc["source"] = source
            doc["content"] = self.read_source(source["file_name"])
            doc["status"] = "current" if version == doc["current_version"] else "superseded"
        return doc

    def list_documents(self, actor, limit=50, offset=0):
        with self.engine.connect() as conn:
            candidates = rows(
                conn,
                select(documents)
                .where(
                    documents.c.organization_id == actor.organization_id,
                    documents.c.revoked.is_(False),
                )
                .order_by(documents.c.name),
            )
            return [d for d in candidates if actor.role in d["roles"]][offset : offset + limit]

    def update_acl(self, actor, document_id, acl, correlation_id):
        require(actor, "owner")
        with transaction(self.engine) as conn:
            doc = row(
                conn,
                select(documents).where(
                    documents.c.id == document_id,
                    documents.c.organization_id == actor.organization_id,
                ),
            )
            if not doc:
                raise DomainError("NOT_FOUND", 404)
            conn.execute(
                documents.update()
                .where(documents.c.id == document_id)
                .values(roles=acl.roles, revoked=acl.revoked)
            )
            record(
                conn,
                actor,
                "document_acl",
                document_id,
                "succeeded",
                correlation_id,
                {"roles": acl.roles, "revoked": acl.revoked},
                now=self.clock(),
            )
        return {"id": document_id, **acl.model_dump()}

    def evidence_allowed(self, actor, evidence, conn=None):
        try:
            doc = self.get_document(actor, evidence["source_id"], conn=conn)
            return doc["current_version"] == evidence["version"]
        except DomainError:
            return False

    def search(self, actor, query):
        store = self.ensure_store()
        with self.engine.connect() as conn:
            candidates = rows(
                conn,
                select(documents).where(
                    documents.c.organization_id == actor.organization_id,
                    documents.c.revoked.is_(False),
                ),
            )
            allowed = [d for d in candidates if actor.role in d["roles"]]
            version_ids = []
            for d in allowed:
                version = row(
                    conn,
                    select(versions).where(
                        versions.c.document_id == d["id"],
                        versions.c.version == d["current_version"],
                        versions.c.state == "indexed",
                        versions.c.index_name == self.index_name,
                    ),
                )
                if version:
                    version_ids.append(version["id"])
        if not version_ids:
            return []
        # Current SQL permissions define the Qdrant filter; no stale copied ACL grants access.
        filt = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.organization_id",
                    match=models.MatchValue(value=actor.organization_id),
                ),
                models.FieldCondition(
                    key="metadata.version_id", match=models.MatchAny(any=version_ids)
                ),
            ]
        )
        try:
            found = store.similarity_search_with_score(
                query, k=5, filter=filt, score_threshold=0.12
            )
        except Exception as exc:
            raise DomainError("RETRIEVAL_UNAVAILABLE", 503, retryable=True) from exc
        evidence = []
        for doc, score in found:
            m = doc.metadata
            candidate = {
                "source_id": m["document_id"],
                "version": m["version"],
                "content_hash": m["content_hash"],
                "fragment": doc.page_content,
                "fragment_ref": f"characters:{m['start']}-{m['end']}",
                "observed_at": m["observed_at"],
                "status": "current",
                "url": f"/api/v1/documents/{m['document_id']}?version={m['version']}",
                "score": float(score),
            }
            if self.evidence_allowed(actor, candidate):
                evidence.append(candidate)
        return evidence
