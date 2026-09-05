import socket
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.auth import get_actor
from app.config import Settings
from app.db import engine_for, heartbeat, migrate
from app.knowledge import Knowledge
from app.main import create_app
from app.services import seed


def pytest_configure(config):
    # pytest creates basetemp itself, but its ignored parent is absent in a clean checkout.
    (Path(config.rootpath) / ".runtime").mkdir(exist_ok=True, mode=0o700)


class Clock:
    def __init__(self):
        self.value = datetime.fromisoformat("2026-09-07T09:00:00+03:00").timestamp()

    def __call__(self):
        return self.value


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch, request):
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker(
        "local_llm"
    ):
        return

    def denied(*args, **kwargs):
        raise AssertionError("Unit/security test attempted a network socket connection")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture
def ctx(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", _env_file=None)
    migrate(settings)
    engine = engine_for(settings)
    clock = Clock()
    qdrant = QdrantClient(":memory:")
    knowledge = Knowledge(engine, settings, client=qdrant, clock=clock)
    seed(engine, settings, knowledge, clock())
    heartbeat(engine, clock())
    app = create_app(settings, engine, knowledge=knowledge, clock=clock)
    with engine.connect() as conn:
        actors = {role: get_actor(conn, role) for role in ("owner", "manager", "employee")}
    with TestClient(app, raise_server_exceptions=False) as client:
        yield {
            "settings": settings,
            "engine": engine,
            "clock": clock,
            "knowledge": knowledge,
            "work": app.state.workflows,
            "client": client,
            "actors": actors,
            "app": app,
        }
    qdrant.close()
    engine.dispose()


def headers(ctx, role="owner"):
    return {
        "Authorization": "Bearer "
        + (ctx["settings"].data_dir / f"{role}.token").read_text().strip()
    }


@pytest.fixture
def owner_headers(ctx):
    return headers(ctx)


@pytest.fixture
def employee_headers(ctx):
    return headers(ctx, "employee")


COMMAND = {
    "text": "Collect three steel offers for project North.",
    "team_id": "procurement",
    "due_at": "2026-09-11T15:00:00+03:00",
}


def propose(ctx, key="command-1"):
    run = ctx["work"].submit(ctx["actors"]["owner"], COMMAND, key, "test")
    ctx["work"].process_one()
    return ctx["work"].get(ctx["actors"]["owner"], run["id"])
