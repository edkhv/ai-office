import argparse
import json
import time

from sqlalchemy import select

from app.auth import issue_credential
from app.backup import data_lease
from app.config import Settings
from app.db import engine_for, migrate, transaction
from app.knowledge import Knowledge
from app.providers import provider_for
from app.schema_v1 import actors, credentials, documents, sessions, versions
from app.services import seed
from app.workspace import initialize, setup_token


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("setup-token")
    token = sub.add_parser("credential")
    token.add_argument("actor")
    revoke = sub.add_parser("revoke-credentials")
    revoke.add_argument("actor")
    sub.add_parser("reindex")
    args = parser.parse_args()
    s = Settings()
    with data_lease(s):
        execute(args, s)


def execute(args, s):
    if args.command == "init":
        migrate(s)
        engine = engine_for(s)
        initialize(engine, s, time.time())
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
            "Pilot initialized without synthetic data. Retrieve the setup token locally with setup-token."
            if s.data_mode == "pilot"
            else "Schema and synthetic fixtures initialized; existing data preserved. Credentials stored in private data volume."
        )
    elif args.command == "setup-token":
        print(setup_token(engine_for(s), s))
    elif args.command == "doctor":
        checks = {
            "mode": s.mode,
            "data_mode": s.data_mode,
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
            conn.execute(sessions.delete().where(sessions.c.actor_id == args.actor))
        print("All actor credentials and associated sessions revoked.")
    elif args.command == "reindex":
        # Explicitly rebuild the active model's collection from immutable current sources.
        from app.auth import get_actor
        from app.db import rows

        engine = engine_for(s)
        k = Knowledge(engine, s)
        k.ensure_store()
        with engine.connect() as conn:
            owner_id = conn.execute(
                select(actors.c.id)
                .where(actors.c.active.is_(True), actors.c.role == "owner")
                .order_by(actors.c.id)
                .limit(1)
            ).scalar()
            if owner_id is None:
                raise SystemExit("Initialize the workspace owner before reindexing.")
            actor = get_actor(conn, owner_id)
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
