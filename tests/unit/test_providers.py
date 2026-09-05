import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.contracts import Command
from app.errors import DomainError
from app.providers import CrewProvider, DemoEmbeddings, DemoProvider, LocalTransport
from tests.conftest import COMMAND


def local(tmp_path, **kwargs):
    return Settings(
        mode="local_ollama",
        embedding_provider="ollama",
        data_dir=tmp_path,
        _env_file=None,
        **kwargs,
    )


def test_ollama_http_contract(tmp_path):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": "response"}})

    adapter = LocalTransport(local(tmp_path), httpx.MockTransport(handle))
    assert adapter.generate([{"role": "user", "content": "hello"}]) == "response"
    payload = json.loads(requests[0].content)
    assert requests[0].url.path == "/api/chat"
    assert payload["stream"] is False and payload["options"]["num_predict"] == 1800
    assert "tools" not in payload


def test_compatible_contract_no_unverified_features(tmp_path):
    settings = Settings(
        mode="compatible_http",
        embedding_provider="ollama",
        inference_base_url="http://127.0.0.1:9999/v1",
        inference_model="test",
        compatible_contract_verified=True,
        data_dir=tmp_path,
        _env_file=None,
    )
    sent = []

    def handle(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    assert (
        LocalTransport(settings, httpx.MockTransport(handle)).generate(
            [{"role": "user", "content": "hello"}]
        )
        == "ok"
    )
    payload = json.loads(sent[0].content)
    assert sent[0].url.path == "/v1/chat/completions"
    assert not {"response_format", "tools", "tool_calls"} & payload.keys()


def test_unconfigured_hardware_contract(tmp_path):
    settings = Settings(
        mode="compatible_http", embedding_provider="ollama", data_dir=tmp_path, _env_file=None
    )
    assert CrewProvider(settings).health() == "not_configured"


def test_redirect_not_followed_and_no_fallback(tmp_path):
    visited = []

    def handle(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://cloud.invalid"})

    provider = CrewProvider(local(tmp_path), httpx.MockTransport(handle))
    assert provider.health() == "degraded"
    assert visited == ["http://127.0.0.1:11434/api/tags"]


def test_timeout_has_safe_error(tmp_path):
    def fail(request):
        raise httpx.ReadTimeout("private error details")

    with pytest.raises(DomainError, match="PROVIDER_UNAVAILABLE"):
        LocalTransport(local(tmp_path), httpx.MockTransport(fail)).generate([])


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254",
        "http://evil.invalid",
        "http://user:secret@localhost",
        "http://localhost?token=secret",
        "file:///etc/passwd",
    ],
)
def test_admin_endpoint_allowlist(url, tmp_path):
    with pytest.raises(ValidationError):
        local(tmp_path, ollama_base_url=url)


def test_demo_cannot_select_real_embeddings(tmp_path):
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, embedding_provider="ollama", _env_file=None)


def test_embedding_spec_and_determinism():
    embed = DemoEmbeddings()
    assert embed.embed_query("Hello") == embed.embed_query("Hello")
    assert len(embed.embed_query("test")) == 512
    assert "demo" in embed.specification


def test_exact_valid_not_invalid(tmp_path, monkeypatch):
    provider = CrewProvider(local(tmp_path))
    plan = DemoProvider().plan(Command(**COMMAND), "ref")
    monkeypatch.setattr(provider, "typed", lambda *args: plan)
    monkeypatch.setattr(provider, "crew_step", lambda *args: "invalid")
    with pytest.raises(DomainError, match="REVIEW_REJECTED"):
        provider.plan(Command(**COMMAND), "ref")


def test_real_crewai_agents_over_mocked_local_transport_no_network(tmp_path):
    plan = DemoProvider().plan(Command(**COMMAND), "ref")
    outputs = iter([plan.model_dump_json(), "valid"])
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": next(outputs)}})

    provider = CrewProvider(local(tmp_path), httpx.MockTransport(handle))
    result = provider.plan(Command(**COMMAND), "ref")
    assert len(result.proposed_tasks) == 3
    assert len(calls) == 2
    assert all("tools" not in p for p in calls)
