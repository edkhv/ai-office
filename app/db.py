import hashlib
import json
import time
import uuid
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.sqlite import insert

from app.schema_v1 import audit, heartbeats


def uid():
    return str(uuid.uuid4())


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def engine_for(settings):
    engine = create_engine(settings.database_url, connect_args={"timeout": 10}, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def configure(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA busy_timeout=10000")

    return engine


@contextmanager
def transaction(engine):
    with engine.connect() as conn:
        conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def migrate(settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def row(conn, stmt):
    value = conn.execute(stmt).mappings().first()
    return dict(value) if value else None


def rows(conn, stmt):
    return [dict(r) for r in conn.execute(stmt).mappings()]


def record(conn, actor, action, target, outcome, correlation_id, safe_diff=None, now=None):
    conn.execute(
        audit.insert().values(
            id=uid(),
            actor_id=actor.id,
            organization_id=actor.organization_id,
            action=action,
            target=target,
            outcome=outcome,
            safe_diff=safe_diff or {},
            timestamp=now if now is not None else time.time(),
            correlation_id=correlation_id,
        )
    )


def heartbeat(engine, now):
    with transaction(engine) as conn:
        stmt = insert(heartbeats).values(id="worker", seen_at=now)
        conn.execute(stmt.on_conflict_do_update(index_elements=["id"], set_={"seen_at": now}))
