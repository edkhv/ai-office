"""Fixed local model routes; runtime containers have no general internet egress."""

import json

import httpx
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from app.agent_runtime import bounded_json
from app.config import Settings
from app.errors import DomainError

ROUTES = {
    ("GET", "api/tags"),
    ("GET", "models"),
    ("POST", "api/chat"),
    ("POST", "api/embed"),
    ("POST", "api/embeddings"),
    ("POST", "chat/completions"),
}


def check_payload(path, payload, settings):
    embed = path in {"api/embed", "api/embeddings"}
    expected = (
        settings.ollama_embedding_model
        if embed
        else settings.inference_model
        if path == "chat/completions"
        else settings.ollama_model
    )
    if not expected or payload.get("model") != expected:
        raise DomainError("MODEL_NOT_ALLOWED", 422)
    common = {"model", "options", "keep_alive"}
    allowed = common | (
        {"input", "prompt", "truncate", "dimensions"}
        if embed
        else {"messages", "stream", "think", "max_tokens", "temperature"}
    )
    if set(payload) - allowed or (
        payload.get("stream") is not None and payload.get("stream") is not False
    ):
        raise DomainError("MODEL_OPTIONS_NOT_ALLOWED", 422)
    options = payload.get("options") or {}
    if isinstance(options, dict):
        # Ollama's SDK serializes unset generation options on embedding requests.
        options = {key: value for key, value in options.items() if value is not None}
    if not isinstance(options, dict) or set(options) - {"temperature", "num_predict", "num_ctx"}:
        raise DomainError("MODEL_OPTIONS_NOT_ALLOWED", 422)
    # Fixed resource budgets are enforced at the boundary, irrespective of SDK defaults.
    if path != "chat/completions":
        payload["keep_alive"] = "5m"
    if embed:
        texts = payload.get("prompt") if path == "api/embeddings" else payload.get("input")
        texts = [texts] if isinstance(texts, str) else texts
        if (
            not isinstance(texts, list)
            or not 1 <= len(texts) <= 64
            or any(not isinstance(text, str) or not text for text in texts)
            or sum(len(text) for text in texts) > 65536
        ):
            raise DomainError("INVALID_EMBEDDING_INPUT", 422)
        dimensions = payload.get("dimensions")
        if dimensions is not None and (type(dimensions) is not int or not 1 <= dimensions <= 8192):
            raise DomainError("INVALID_EMBEDDING_DIMENSIONS", 422)
        payload.pop("options", None)
        if path == "api/embed":
            payload["truncate"] = False
    else:
        messages = payload.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 30:
            raise DomainError("INVALID_MODEL_MESSAGES", 422)
        for message in messages:
            if (
                not isinstance(message, dict)
                or set(message) - {"role", "content"}
                or message.get("role") not in ("system", "user", "assistant")
                or not isinstance(message.get("content"), str)
            ):
                raise DomainError("INVALID_MODEL_MESSAGES", 422)
        payload["stream"] = False
        if path == "api/chat":
            payload["options"] = {"temperature": 0, "num_predict": 1800, "num_ctx": 8192}
            payload["think"] = False
        else:
            payload.pop("options", None)
            payload.pop("keep_alive", None)
            payload.pop("think", None)
            payload["max_tokens"] = 1800
            payload["temperature"] = 0
    return payload


def create_app(settings=None, transport=None):
    settings = settings or Settings()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    @app.get("/health")
    def health():
        return {"status": "ready"}

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def proxy(path: str, request: Request):
        if (request.method, path) not in ROUTES or request.query_params:
            raise DomainError("MODEL_ROUTE_NOT_ALLOWED", 404)
        if path in {"models", "chat/completions"}:
            if not settings.compatible_contract_verified or not settings.inference_base_url:
                raise DomainError("NOT_CONFIGURED", 503)
            base = settings.check_url(settings.inference_base_url)
        else:
            base = settings.check_url(settings.ollama_base_url)
        payload = None
        if request.method == "POST":
            payload = check_payload(path, await bounded_json(request, 1048576), settings)
        try:
            async with httpx.AsyncClient(
                timeout=settings.provider_timeout,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            ) as client:
                async with client.stream(request.method, base + "/" + path, json=payload) as reply:
                    reply.raise_for_status()
                    content = bytearray()
                    async for chunk in reply.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 16777216:
                            raise DomainError("MODEL_RESPONSE_TOO_LARGE", 503)
                    json.loads(content)
                    return Response(bytes(content), media_type="application/json")
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise DomainError("MODEL_GATEWAY_UNAVAILABLE", 503) from exc

    return app
