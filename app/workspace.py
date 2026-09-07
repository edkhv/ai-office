"""Single-company initialization and owner-managed accounts."""

import secrets

from sqlalchemy import func, select

from app.auth import get_actor, require, write_private
from app.db import digest, record, row, rows, transaction, uid
from app.errors import DomainError
from app.schema_v1 import actors, credentials, documents, ledger, sessions
from app.workspace_schema import user_profiles, workspace_profiles


def profile(conn):
    return row(conn, select(workspace_profiles).where(workspace_profiles.c.id == "workspace"))


def public_profile(value):
    return {key: value[key] for key in ("organization_id", "company_name", "timezone", "data_mode")}


def initialize(engine, settings, now):
    """Persist mode before loading data. Never convert an existing data volume."""
    with transaction(engine) as conn:
        current = profile(conn)
        if current:
            if current["data_mode"] != settings.data_mode:
                raise DomainError(
                    "DATA_MODE_MISMATCH", 409, "Use a separate data volume for pilot and demo."
                )
            return
        occupied = any(
            conn.execute(select(table.c.id).limit(1)).first()
            for table in (actors, documents, ledger)
        )
        if occupied:
            raise DomainError("WORKSPACE_INITIALIZATION_REQUIRED", 409)
        is_demo = settings.data_mode == "demo"
        conn.execute(
            workspace_profiles.insert().values(
                id="workspace",
                organization_id="northline" if is_demo else None,
                company_name="Northline Demo" if is_demo else None,
                timezone=settings.org_timezone,
                data_mode=settings.data_mode,
                setup_digest=None,
                setup_completed=is_demo,
                created_at=now,
            )
        )
    if not is_demo:
        setup_token(engine, settings)


def setup_token(engine, settings):
    """Local administrative recovery rotates the unfinished setup token only."""
    token = secrets.token_urlsafe(36)
    path = settings.data_dir / "setup.token"
    with transaction(engine) as conn:
        current = profile(conn)
        if not current or current["data_mode"] != "pilot" or current["setup_completed"]:
            raise DomainError("SETUP_UNAVAILABLE", 409)
        # Remove only this exact local administrative credential, never follow symlinks.
        if path.exists() or path.is_symlink():
            path.unlink()
        write_private(path, token + "\n")
        conn.execute(
            workspace_profiles.update()
            .where(workspace_profiles.c.id == "workspace")
            .values(setup_digest=digest(token))
        )
    return token


def status(engine, settings):
    with engine.connect() as conn:
        current = profile(conn)
    return {
        "needs_setup": bool(
            current and current["data_mode"] == "pilot" and not current["setup_completed"]
        ),
        "data_mode": current["data_mode"] if current else settings.data_mode,
    }


def _credential(conn, settings, actor_id, now):
    token = secrets.token_urlsafe(36)
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


def complete_setup(engine, settings, body, now, correlation_id):
    with transaction(engine) as conn:
        current = profile(conn)
        if not current or current["data_mode"] != "pilot" or current["setup_completed"]:
            raise DomainError("SETUP_UNAVAILABLE", 409)
        if not current["setup_digest"] or not secrets.compare_digest(
            current["setup_digest"], digest(body.token)
        ):
            raise DomainError("INVALID_SETUP_TOKEN", 401)
        if conn.execute(select(actors.c.id).limit(1)).first():
            raise DomainError("SETUP_UNAVAILABLE", 409)
        org_id, actor_id = uid(), uid()
        conn.execute(
            actors.insert().values(
                id=actor_id, organization_id=org_id, role="owner", team_id="operations", active=True
            )
        )
        conn.execute(
            user_profiles.insert().values(actor_id=actor_id, display_name=body.owner_display_name)
        )
        conn.execute(
            workspace_profiles.update()
            .where(workspace_profiles.c.id == "workspace")
            .values(
                organization_id=org_id,
                company_name=body.company_name,
                timezone=body.timezone,
                setup_completed=True,
                setup_digest=None,
            )
        )
        token = _credential(conn, settings, actor_id, now)
        actor = get_actor(conn, actor_id)
        record(conn, actor, "workspace_setup", org_id, "succeeded", correlation_id, now=now)
        result = {
            "workspace": public_profile(profile(conn)),
            "user": _user(conn, actor_id, org_id),
            "credential": token,
        }
    # Token has already been consumed atomically even if local cleanup fails.
    try:
        (settings.data_dir / "setup.token").unlink(missing_ok=True)
    except OSError:
        pass
    return result


def _fresh_owner(conn, actor):
    fresh = get_actor(conn, actor.id)
    require(fresh, "owner")
    current = profile(conn)
    if not current or fresh.organization_id != current["organization_id"]:
        raise DomainError("FORBIDDEN", 403)
    return fresh


def _user(conn, actor_id, org_id):
    target = row(
        conn, select(actors).where(actors.c.id == actor_id, actors.c.organization_id == org_id)
    )
    if not target:
        raise DomainError("NOT_FOUND", 404)
    metadata = row(conn, select(user_profiles).where(user_profiles.c.actor_id == actor_id))
    return {**target, "display_name": metadata["display_name"] if metadata else target["id"]}


def info(engine, actor):
    with engine.connect() as conn:
        fresh = get_actor(conn, actor.id)
        current = profile(conn)
        if not current or current["organization_id"] != fresh.organization_id:
            raise DomainError("FORBIDDEN", 403)
        return {
            **public_profile(current),
            "current_user": _user(conn, fresh.id, fresh.organization_id),
        }


def list_users(engine, actor):
    with engine.connect() as conn:
        fresh = _fresh_owner(conn, actor)
        return [
            _user(conn, item["id"], fresh.organization_id)
            for item in rows(
                conn,
                select(actors.c.id)
                .where(actors.c.organization_id == fresh.organization_id)
                .order_by(actors.c.id),
            )
        ]


def create_user(engine, settings, actor, body, now, correlation_id):
    with transaction(engine) as conn:
        fresh = _fresh_owner(conn, actor)
        actor_id = uid()
        conn.execute(
            actors.insert().values(
                id=actor_id,
                organization_id=fresh.organization_id,
                role=body.role,
                team_id=body.team_id,
                active=True,
            )
        )
        conn.execute(
            user_profiles.insert().values(actor_id=actor_id, display_name=body.display_name)
        )
        token = _credential(conn, settings, actor_id, now)
        record(
            conn,
            fresh,
            "user_create",
            actor_id,
            "succeeded",
            correlation_id,
            {"role": body.role, "team_id": body.team_id},
            now=now,
        )
        return {"user": _user(conn, actor_id, fresh.organization_id), "credential": token}


def _revoke(conn, actor_id):
    conn.execute(
        credentials.update().where(credentials.c.actor_id == actor_id).values(revoked=True)
    )
    conn.execute(sessions.delete().where(sessions.c.actor_id == actor_id))


def update_user(engine, actor, actor_id, body, now, correlation_id):
    with transaction(engine) as conn:
        fresh = _fresh_owner(conn, actor)
        target = _user(conn, actor_id, fresh.organization_id)
        changes = body.model_dump(exclude_none=True)
        values = {key: value for key, value in changes.items() if key != "display_name"}
        if (
            target["active"]
            and target["role"] == "owner"
            and (values.get("active") is False or values.get("role", "owner") != "owner")
        ):
            owners = conn.execute(
                select(func.count())
                .select_from(actors)
                .where(
                    actors.c.organization_id == fresh.organization_id,
                    actors.c.role == "owner",
                    actors.c.active.is_(True),
                )
            ).scalar_one()
            if owners <= 1:
                raise DomainError("LAST_ACTIVE_OWNER", 409)
        if values:
            conn.execute(actors.update().where(actors.c.id == actor_id).values(**values))
        if "display_name" in changes:
            if row(conn, select(user_profiles).where(user_profiles.c.actor_id == actor_id)):
                conn.execute(
                    user_profiles.update()
                    .where(user_profiles.c.actor_id == actor_id)
                    .values(display_name=changes["display_name"])
                )
            else:
                conn.execute(
                    user_profiles.insert().values(
                        actor_id=actor_id, display_name=changes["display_name"]
                    )
                )
        changed_access = any(target[key] != value for key, value in values.items())
        if changed_access:
            _revoke(conn, actor_id)
        record(
            conn,
            fresh,
            "user_update",
            actor_id,
            "succeeded",
            correlation_id,
            {"fields": sorted(changes), "access_revoked": changed_access},
            now=now,
        )
        return _user(conn, actor_id, fresh.organization_id)


def rotate_credential(engine, settings, actor, actor_id, now, correlation_id):
    with transaction(engine) as conn:
        fresh = _fresh_owner(conn, actor)
        target = _user(conn, actor_id, fresh.organization_id)
        if not target["active"]:
            raise DomainError("USER_INACTIVE", 409)
        _revoke(conn, actor_id)
        token = _credential(conn, settings, actor_id, now)
        record(conn, fresh, "credential_rotate", actor_id, "succeeded", correlation_id, now=now)
        return {"user": target, "credential": token}


def validate_mode(engine, settings):
    """Reject accidental data-volume/config mixing on server and worker entry points."""
    with engine.connect() as conn:
        current = profile(conn)
    if not current:
        raise DomainError("WORKSPACE_INITIALIZATION_REQUIRED", 503)
    if current["data_mode"] != settings.data_mode:
        raise DomainError("DATA_MODE_MISMATCH", 503, "Use the matching data mode and data volume.")
