import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import select

from app import workspace
from app.auth import authenticate, get_actor, login
from app.config import Settings
from app.db import engine_for, migrate, row, transaction
from app.errors import DomainError
from app.knowledge import Knowledge
from app.main import create_app
from app.schema_v1 import actors, audit, credentials, documents, ledger
from app.services import briefing, metrics, seed
from app.workspace_contracts import Setup, UserCreate, UserUpdate


@pytest.fixture
def pilot(tmp_path):
    settings = Settings(data_mode="pilot", data_dir=tmp_path / "pilot", _env_file=None)
    migrate(settings)
    engine = engine_for(settings)
    workspace.initialize(engine, settings, 1000)
    yield engine, settings
    engine.dispose()


def finish(pilot):
    engine, settings = pilot
    body = Setup(
        token=(settings.data_dir / "setup.token").read_text().strip(),
        company_name="Компания",
        owner_display_name="Руководитель",
        timezone="Europe/Moscow",
    )
    result = workspace.complete_setup(engine, settings, body, 1000, "test")
    with engine.connect() as conn:
        owner = get_actor(conn, result["user"]["id"])
    return owner, result


def test_pilot_init_contains_no_fixtures_and_private_setup(pilot):
    engine, settings = pilot
    with engine.connect() as conn:
        for table in (actors, documents, ledger, credentials, audit):
            assert conn.execute(select(table)).first() is None
    assert stat.S_IMODE((settings.data_dir / "setup.token").stat().st_mode) == 0o600
    assert workspace.status(engine, settings) == {"needs_setup": True, "data_mode": "pilot"}
    seed(engine, settings, None, 1000)
    assert workspace.status(engine, settings)["needs_setup"]


def test_setup_requires_private_token_consumed_once(pilot):
    engine, settings = pilot
    with pytest.raises(DomainError) as error:
        workspace.complete_setup(
            engine,
            settings,
            Setup(token="x" * 48, company_name="Bad", owner_display_name="Bad"),
            1000,
            "test",
        )
    assert error.value.code == "INVALID_SETUP_TOKEN"
    owner, result = finish(pilot)
    assert result["workspace"]["company_name"] == "Компания"
    assert authenticate(engine, result["credential"], 1001) == owner
    assert not (settings.data_dir / "setup.token").exists()
    with engine.connect() as conn:
        assert workspace.profile(conn)["setup_digest"] is None
        assert result["credential"] not in str(conn.execute(select(audit)).all())
    with pytest.raises(DomainError):
        workspace.complete_setup(
            engine,
            settings,
            Setup(token="x" * 48, company_name="Takeover", owner_display_name="Bad"),
            1000,
            "test",
        )
    with pytest.raises(DomainError):
        workspace.setup_token(engine, settings)


def test_parallel_setup_exactly_one_owner(pilot):
    engine, settings = pilot
    body = Setup(
        token=(settings.data_dir / "setup.token").read_text().strip(),
        company_name="Company",
        owner_display_name="Owner",
    )

    def attempt():
        try:
            return workspace.complete_setup(engine, settings, body, 1000, "race")
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "SETUP_UNAVAILABLE" in results
    with engine.connect() as conn:
        assert len(conn.execute(select(actors)).all()) == 1


def test_pilot_finance_unavailable_not_synthetic(pilot):
    engine, _ = pilot
    owner, _ = finish(pilot)
    assert metrics(engine, owner, 1000) == []
    value = briefing(engine, owner, 1000, "test")
    assert value["facts"] == []
    assert value["finance_status"] == "unavailable"
    assert value["finance_synthetic"] is False
    assert value["source_as_of"] is None
    assert "northline" not in str(value).lower()


def test_mode_change_refused(pilot, ctx):
    engine, settings = pilot
    with pytest.raises(DomainError, match="DATA_MODE_MISMATCH"):
        workspace.initialize(engine, settings.model_copy(update={"data_mode": "demo"}), 1000)
    with pytest.raises(DomainError):
        seed(ctx["engine"], ctx["settings"].model_copy(update={"data_mode": "pilot"}), None, 1000)


def test_manage_users_rotate_disable_and_last_owner(pilot):
    engine, settings = pilot
    owner, _ = finish(pilot)
    created = workspace.create_user(
        engine,
        settings,
        owner,
        UserCreate(display_name="Иван", team_id="procurement"),
        1000,
        "test",
    )
    employee = authenticate(engine, created["credential"], 1001)
    _, cookie, csrf = login(engine, settings, created["credential"], "local", 1001, "test")
    assert authenticate(engine, cookie, 1002, cookie=True, csrf=csrf, mutation=True) == employee
    workspace.update_user(engine, owner, employee.id, UserUpdate(role="manager"), 1002, "test")
    for token, is_cookie in ((cookie, True), (created["credential"], False)):
        with pytest.raises(DomainError):
            authenticate(engine, token, 1003, cookie=is_cookie)
    rotated = workspace.rotate_credential(engine, settings, owner, employee.id, 1003, "test")
    assert authenticate(engine, rotated["credential"], 1004).role == "manager"
    workspace.update_user(engine, owner, employee.id, UserUpdate(active=False), 1005, "test")
    with pytest.raises(DomainError):
        authenticate(engine, rotated["credential"], 1006)
    with pytest.raises(DomainError):
        workspace.rotate_credential(engine, settings, owner, employee.id, 1006, "test")
    with pytest.raises(DomainError) as error:
        workspace.update_user(engine, owner, owner.id, UserUpdate(active=False), 1006, "test")
    assert error.value.code == "LAST_ACTIVE_OWNER"
    assert len(workspace.list_users(engine, owner)) == 2


def test_owner_scope_fresh_role_and_cross_org(pilot):
    engine, settings = pilot
    owner, _ = finish(pilot)
    other = workspace.create_user(
        engine, settings, owner, UserCreate(display_name="Other", role="owner"), 1000, "test"
    )
    old_owner = owner
    workspace.update_user(engine, owner, owner.id, UserUpdate(role="employee"), 1001, "test")
    with pytest.raises(DomainError):
        workspace.create_user(
            engine, settings, old_owner, UserCreate(display_name="Denied"), 1001, "test"
        )
    with engine.connect() as conn:
        owner = get_actor(conn, other["user"]["id"])
    with transaction(engine) as conn:
        conn.execute(
            actors.insert().values(
                id="foreign",
                organization_id="another",
                role="owner",
                team_id="operations",
                active=True,
            )
        )
    with pytest.raises(DomainError) as error:
        workspace.update_user(engine, owner, "foreign", UserUpdate(active=False), 1000, "test")
    assert error.value.status == 404
    with engine.connect() as conn:
        foreign = get_actor(conn, "foreign")
    with pytest.raises(DomainError):
        workspace.list_users(engine, foreign)


def test_demo_seed_does_not_reactivate_disabled_original_owner(ctx):
    engine, settings = ctx["engine"], ctx["settings"]
    owner = ctx["actors"]["owner"]
    workspace.create_user(
        engine,
        settings,
        owner,
        UserCreate(display_name="Replacement", role="owner"),
        ctx["clock"](),
        "test",
    )
    workspace.update_user(engine, owner, owner.id, UserUpdate(active=False), ctx["clock"](), "test")
    seed(engine, settings, ctx["knowledge"], ctx["clock"]())
    with engine.connect() as conn:
        assert row(conn, select(actors).where(actors.c.id == "owner"))["active"] is False


def test_setup_http_contract_and_no_public_user_management(pilot):
    engine, settings = pilot
    qdrant = QdrantClient(":memory:")
    knowledge = Knowledge(engine, settings, client=qdrant, clock=lambda: 1000)
    app = create_app(settings, engine, knowledge=knowledge, clock=lambda: 1000)
    with TestClient(app) as client:
        status = client.get("/api/v1/setup/status")
        assert status.status_code == 200
        assert "token" not in status.text
        assert client.get("/api/v1/users").status_code == 401
        response = client.post(
            "/api/v1/setup",
            json={
                "token": (settings.data_dir / "setup.token").read_text().strip(),
                "company_name": "Customer",
                "owner_display_name": "Owner",
            },
        )
        assert response.status_code == 201
        value = response.json()
        headers = {"Authorization": "Bearer " + value["credential"]}
        assert client.get("/api/v1/workspace", headers=headers).json()["company_name"] == "Customer"
        assert client.get("/api/v1/users", headers=headers).json()[0]["display_name"] == "Owner"
    qdrant.close()


def test_migrate_existing_demo_keeps_data_and_sets_demo_profile(tmp_path):
    from alembic import command
    from alembic.config import Config

    settings = Settings(data_dir=tmp_path / "upgrade", _env_file=None)
    settings.data_dir.mkdir()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "0004_task_assignments")
    engine = engine_for(settings)
    with transaction(engine) as conn:
        conn.execute(
            actors.insert().values(
                id="owner",
                organization_id="northline",
                role="owner",
                team_id="operations",
                active=True,
            )
        )
    migrate(settings)
    with engine.connect() as conn:
        current = workspace.profile(conn)
        assert current["data_mode"] == "demo"
        assert current["setup_completed"]
        assert current["setup_digest"] is None
        assert get_actor(conn, "owner").organization_id == "northline"
    assert not (settings.data_dir / "setup.token").exists()
    engine.dispose()


def test_validate_mode_rejects_accidental_runtime_mismatch(pilot):
    engine, settings = pilot
    workspace.validate_mode(engine, settings)
    with pytest.raises(DomainError) as error:
        workspace.validate_mode(engine, settings.model_copy(update={"data_mode": "demo"}))
    assert error.value.code == "DATA_MODE_MISMATCH"
