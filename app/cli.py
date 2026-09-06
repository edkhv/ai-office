import argparse
import json
import time

from sqlalchemy import select

from app.auth import issue_credential
from app.config import Settings
from app.db import engine_for, migrate, transaction
from app.knowledge import Knowledge
from app.providers import provider_for
from app.schema_v1 import credentials, documents, versions
from app.services import seed


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    token = sub.add_parser("credential")
    token.add_argument("actor", choices=["owner", "manager", "employee"])
    revoke = sub.add_parser("revoke-credentials")
    revoke.add_argument("actor", choices=["owner", "manager", "employee"])
    sub.add_parser("reindex")
    args = parser.parse_args()
    s = Settings()
    if args.command == "init":
        migrate(s)
        engine = engine_for(s)
        knowledge = Knowledge(engine, s)
        for attempt in range(20):
            try:
                knowledge.ensure_store()
                break
            except Exception:
                if attempt == 19:
                    raise SystemExit(
                        "Qdrant/embedding initialization failed; run doctor."
                    ) from None
                time.sleep(1)
        seed(engine, s, knowledge, time.time())
        print(
            "Schema and synthetic fixtures initialized; existing data preserved. Credentials stored in private data volume."
        )
    elif args.command == "doctor":
        checks = {
            "mode": s.mode,
            "provider": provider_for(s).health(),
            "hardware": "hardware_validation_pending",
        }
        try:
            engine = engine_for(s)
            with engine.connect() as conn:
                conn.execute(select(documents.c.id).limit(1))
            Knowledge(engine, s).ensure_store()
            checks["storage"] = "ready"
        except Exception:
            checks["storage"] = "degraded"
        print(json.dumps(checks, indent=2))
    elif args.command == "credential":
        print(issue_credential(engine_for(s), s, args.actor, time.time()))
    elif args.command == "revoke-credentials":
        with transaction(engine_for(s)) as conn:
            conn.execute(
                credentials.update()
                .where(credentials.c.actor_id == args.actor)
                .values(revoked=True)
            )
        print("All actor credentials and associated sessions revoked.")
    elif args.command == "reindex":
        # Explicitly rebuild the active model's collection from immutable current sources.
        from app.auth import get_actor
        from app.db import rows

        engine = engine_for(s)
        k = Knowledge(engine, s)
        k.ensure_store()
        with engine.connect() as conn:
            actor = get_actor(conn, "owner")
            docs = rows(conn, select(documents).where(documents.c.revoked.is_(False)))
        for doc in docs:
            source = k.get_document(actor, doc["id"], doc["current_version"])
            original = k.original_document(actor, doc["id"], doc["current_version"])
            with transaction(engine) as conn:
                conn.execute(
                    versions.update()
                    .where(versions.c.id == source["source"]["id"])
                    .values(state="pending")
                )
            k.import_document(
                actor,
                original["filename"] if original["original_preserved"] else doc["name"],
                original["content"],
                doc["roles"],
                "reindex",
                doc["id"],
                content_type=original["media_type"],
            )
        print("Current sources indexed for the configured embedding specification.")


if __name__ == "__main__":
    main()
