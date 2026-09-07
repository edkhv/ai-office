import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent_runtime import create_app as runtime_app
from app.config import Settings
from app.errors import DomainError
from app.model_gateway import create_app as gateway_app
from app.providers import CrewProvider


def settings(tmp_path, **kwargs):
    return Settings(
        _env_file=None,
        mode="local_ollama",
        embedding_provider="ollama",
        data_dir=tmp_path,
        **kwargs,
    )


def test_pilot_cannot_fall_back_to_in_process_sdk(tmp_path, monkeypatch):
    provider = CrewProvider(settings(tmp_path, data_mode="pilot"))
    monkeypatch.setattr(
        provider, "_sdk_step", lambda *args: pytest.fail("SDK called in core pilot")
    )
    assert provider.health() == "not_configured"
    with pytest.raises(DomainError, match="AGENT_RUNTIME_REQUIRED"):
        provider.crew_step("Planner", "private instruction")


def test_core_dispatches_only_minimum_text_and_checks_model(tmp_path):
    sent = []

    def handle(request):
        sent.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ready", "model_id": "qwen3:8b"})
        return httpx.Response(200, json={"output": "valid", "model_id": "qwen3:8b"})

    provider = CrewProvider(
        settings(tmp_path, data_mode="pilot", agent_runtime_url="http://agent-runtime:8001"),
        httpx.MockTransport(handle),
    )
    assert provider.health() == "ready"
    assert provider.crew_step("Reviewer", "review authorized text") == "valid"
    assert json.loads(sent[-1].content) == {
        "role": "Reviewer",
        "instruction": "review authorized text",
    }
    assert "authorization" not in sent[-1].headers
    assert sent[-1].url.host == "agent-runtime"


@pytest.mark.parametrize(
    "reply", [{"output": "ok", "model_id": "other"}, {"output": 3, "model_id": "qwen3:8b"}]
)
def test_runtime_response_contract(tmp_path, reply):
    provider = CrewProvider(
        settings(tmp_path, agent_runtime_url="http://agent-runtime:8001"),
        httpx.MockTransport(lambda request: httpx.Response(200, json=reply)),
    )
    with pytest.raises(DomainError, match="AGENT_RUNTIME_SCHEMA_ERROR"):
        provider.crew_step("Reviewer", "test")


def test_runtime_redirect_not_followed(tmp_path):
    sent = []

    def redirect(request):
        sent.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://unexpected.invalid"})

    provider = CrewProvider(
        settings(tmp_path, agent_runtime_url="http://agent-runtime:8001"),
        httpx.MockTransport(redirect),
    )
    with pytest.raises(DomainError, match="AGENT_RUNTIME_UNAVAILABLE"):
        provider.crew_step("Reviewer", "test")
    assert sent == ["http://agent-runtime:8001/step"]


def test_runtime_fixed_routes_validation_and_safe_sdk_failure(tmp_path):
    class FakeProvider:
        model_id = "qwen3:8b"

        def _sdk_step(self, role, instruction):
            if instruction == "fail":
                raise RuntimeError("private customer source in SDK error")
            return "valid"

    client = TestClient(runtime_app(settings(tmp_path), FakeProvider()))
    assert client.get("/api/v2/tenants/default/databases/default/collections").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.post("/step", json={"role": "Shell", "instruction": "x"}).status_code == 422
    assert (
        client.post("/step", json={"role": "Planner", "instruction": "x", "tools": []}).status_code
        == 422
    )
    assert client.post("/step", content=b"x" * 65537).status_code == 413
    result = client.post("/step", json={"role": "Reviewer", "instruction": "fail"})
    assert result.status_code == 503
    assert "private customer" not in result.text
    assert (
        client.post("/step", json={"role": "Reviewer", "instruction": "x"}).json()["output"]
        == "valid"
    )


def test_gateway_pins_models_routes_and_resource_budgets(tmp_path):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    client = TestClient(gateway_app(settings(tmp_path), httpx.MockTransport(handle)))
    payload = {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "x"}],
        "options": {"num_ctx": 9999999},
    }
    assert client.post("/api/chat", json=payload).status_code == 200
    assert json.loads(seen[-1].content)["options"]["num_ctx"] == 8192
    assert seen[-1].url == "http://127.0.0.1:11434/api/chat"
    before = len(seen)
    assert client.post("/api/pull", json={"model": "remote"}).status_code == 404
    assert client.post("/api/chat?url=https://evil.invalid", json=payload).status_code == 404
    assert client.post("/api/chat", json={**payload, "model": "unknown"}).status_code == 422
    assert client.post("/api/chat", json={**payload, "tools": []}).status_code == 422
    assert client.post("/api/chat", json={**payload, "stream": True}).status_code == 422
    assert (
        client.post(
            "/api/chat", json={**payload, "messages": [{"role": "tool", "content": "x"}]}
        ).status_code
        == 422
    )
    assert client.post("/api/chat", content=b"x" * 1048577).status_code == 413
    assert len(seen) == before


def test_gateway_embeddings_and_compatible_base_path(tmp_path):
    visited = []

    def handle(request):
        visited.append(request)
        return httpx.Response(200, json={"embeddings": [[1, 2]]})

    configured = settings(
        tmp_path,
        inference_base_url="http://localhost:9999/v1",
        inference_model="allowed",
        compatible_contract_verified=True,
    )
    client = TestClient(gateway_app(configured, httpx.MockTransport(handle)))
    assert (
        client.post(
            "/api/embed", json={"model": "mxbai-embed-large", "input": ["authorized fragment"]}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/chat/completions",
            json={"model": "allowed", "messages": [{"role": "user", "content": "x"}]},
        ).status_code
        == 200
    )
    assert visited[-1].url == "http://localhost:9999/v1/chat/completions"
    assert "authorization" not in visited[-1].headers


def test_gateway_no_redirect_or_upstream_error_leak(tmp_path):
    visited = []

    def handle(request):
        visited.append(request)
        return httpx.Response(302, headers={"location": "https://private.invalid"})

    client = TestClient(gateway_app(settings(tmp_path), httpx.MockTransport(handle)))
    reply = client.get("/api/tags")
    assert reply.status_code == 503
    assert "private.invalid" not in reply.text
    assert len(visited) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"input": ["x"] * 65},
        {"input": "x" * 65537},
        {"input": [3]},
        {"dimensions": 0},
        {"dimensions": 8193},
        {"dimensions": True},
        {"model": "http://qdrant:6333/collections"},
    ],
)
def test_gateway_rejects_unbounded_embedding_requests(tmp_path, change):
    def unexpected(request):
        pytest.fail("Rejected embedding request reached upstream")

    client = TestClient(gateway_app(settings(tmp_path), httpx.MockTransport(unexpected)))
    payload = {"model": "mxbai-embed-large", "input": ["x"], **change}
    assert client.post("/api/embed", json=payload).status_code == 422


def test_gateway_embedding_resources_are_pinned(tmp_path):
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[1.0]]})

    client = TestClient(gateway_app(settings(tmp_path), httpx.MockTransport(handle)))
    assert (
        client.post(
            "/api/embed",
            json={
                "model": "mxbai-embed-large",
                "input": ["x"],
                "keep_alive": -1,
                "truncate": True,
                "options": {"num_ctx": 999999},
            },
        ).status_code
        == 200
    )
    assert sent[-1]["keep_alive"] == "5m"
    assert sent[-1]["truncate"] is False
    assert "options" not in sent[-1]


def test_pilot_deterministic_plan_does_not_invent_demo_company(tmp_path):
    from app.contracts import Command
    from app.providers import provider_for
    from tests.conftest import COMMAND

    pilot = Settings(_env_file=None, data_mode="pilot", data_dir=tmp_path)
    result = provider_for(pilot).plan(Command(**COMMAND), "ref")
    assert result.missing_fields
    assert not result.proposed_tasks
    assert not result.proposed_messages
    assert "North" not in result.model_dump_json()


def test_actual_crewai_message_metadata_and_ollama_embedding_sdk_contract(tmp_path):
    from langchain_ollama import OllamaEmbeddings

    sent = []

    def handle(request):
        from app.model_gateway import check_payload

        payload = json.loads(request.content)
        check_payload(request.url.path.lstrip("/"), payload, settings(tmp_path))
        sent.append(payload)
        result = (
            {"embeddings": [[1.0]]}
            if request.url.path == "/api/embed"
            else {"message": {"content": "valid"}}
        )
        return httpx.Response(200, json=result)

    transport = httpx.MockTransport(handle)
    assert (
        CrewProvider(settings(tmp_path), transport)._sdk_step("Reviewer", "Reply valid.") == "valid"
    )
    assert all(set(message) == {"role", "content"} for message in sent[-1]["messages"])
    model = OllamaEmbeddings(model="mxbai-embed-large", client_kwargs={"transport": transport})
    assert model.embed_documents(["x"]) == [[1.0]]
