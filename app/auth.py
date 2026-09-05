import secrets
from pathlib import Path

from sqlalchemy import select

from app.contracts import Actor
from app.db import digest, record, row, transaction, uid
from app.errors import DomainError
from app.schema_v1 import actors, credentials, login_limits, sessions


def get_actor(conn, actor_id):
    result = row(conn, select(actors).where(actors.c.id == actor_id, actors.c.active.is_(True)))
    if not result:
        raise DomainError("UNAUTHORIZED", 401)
    return Actor(**{k: result[k] for k in ("id", "organization_id", "role", "team_id")})


def require(actor, *roles):
    if actor.role not in roles:
        raise DomainError("FORBIDDEN", 403)


def issue_credential(engine, settings, actor_id, now):
    token = secrets.token_urlsafe(36)
    with transaction(engine) as conn:
        get_actor(conn, actor_id)
        conn.execute(
            credentials.insert().values(
                id=uid(),
                actor_id=actor_id,
                digest=digest(token),
                expires_at=now + settings.credential_days * 86400,
                revoked=False,
            )
        )
    return token


def write_private(path: Path, text: str):
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(text)


def authenticate(engine, token, now, cookie=False, csrf=None, mutation=False):
    with engine.connect() as conn:
        if cookie:
            session = row(
                conn,
                select(sessions).where(
                    sessions.c.digest == digest(token), sessions.c.expires_at > now
                ),
            )
            if not session:
                raise DomainError("UNAUTHORIZED", 401)
            credential = row(
                conn,
                select(credentials).where(
                    credentials.c.id == session["credential_id"],
                    credentials.c.revoked.is_(False),
                    credentials.c.expires_at > now,
                ),
            )
            if not credential:
                raise DomainError("UNAUTHORIZED", 401)
            if mutation and (
                not csrf or not secrets.compare_digest(session["csrf_digest"], digest(csrf))
            ):
                raise DomainError("CSRF_REJECTED", 403)
            return get_actor(conn, session["actor_id"])
        credential = row(
            conn,
            select(credentials).where(
                credentials.c.digest == digest(token),
                credentials.c.revoked.is_(False),
                credentials.c.expires_at > now,
            ),
        )
        if not credential:
            raise DomainError("UNAUTHORIZED", 401)
        return get_actor(conn, credential["actor_id"])


def login(engine, settings, token, remote, now, correlation_id):
    # Persist attempts before checking the credential so failures cannot roll back the limit.
    bucket = digest(remote)
    with transaction(engine) as conn:
        limit = row(conn, select(login_limits).where(login_limits.c.id == bucket))
        if limit and limit["reset_at"] > now and limit["attempts"] >= 10:
            raise DomainError("LOGIN_RATE_LIMIT", 429)
        if not limit:
            conn.execute(login_limits.insert().values(id=bucket, attempts=1, reset_at=now + 60))
        else:
            conn.execute(
                login_limits.update()
                .where(login_limits.c.id == bucket)
                .values(
                    attempts=limit["attempts"] + 1 if limit["reset_at"] > now else 1,
                    reset_at=limit["reset_at"] if limit["reset_at"] > now else now + 60,
                )
            )
    actor = authenticate(engine, token, now)
    session_token, csrf = secrets.token_urlsafe(36), secrets.token_urlsafe(24)
    with transaction(engine) as conn:
        cred = row(
            conn,
            select(credentials).where(
                credentials.c.digest == digest(token),
                credentials.c.revoked.is_(False),
                credentials.c.expires_at > now,
            ),
        )
        if not cred:
            raise DomainError("UNAUTHORIZED", 401)
        conn.execute(
            sessions.insert().values(
                id=uid(),
                actor_id=actor.id,
                credential_id=cred["id"],
                digest=digest(session_token),
                csrf_digest=digest(csrf),
                expires_at=min(now + settings.session_seconds, cred["expires_at"]),
            )
        )
        record(conn, actor, "login", actor.id, "succeeded", correlation_id, now=now)
    return actor, session_token, csrf
