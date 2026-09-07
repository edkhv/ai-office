"""Private, data-only CrewAI boundary. Never mount the business data directory here."""

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.config import Settings
from app.errors import DomainError
from app.providers import CrewProvider


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["Planner", "Reviewer", "Evidence analyst", "Quote preparation assistant"]
    instruction: str = Field(min_length=1, max_length=60000)


async def bounded_json(request: Request, limit: int):
    if request.query_params:
        raise DomainError("QUERY_NOT_ALLOWED", 400)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > limit:
            raise DomainError("REQUEST_TOO_LARGE", 413)
    try:
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError) as exc:
        raise DomainError("INVALID_REQUEST", 422) from exc


def create_app(settings=None, provider=None):
    settings = settings or Settings()
    # No recursive remote calls; SDK consent/replay location is independent of business storage.
    isolated = settings.model_copy(
        update={
            "agent_runtime_url": "",
            "data_mode": "demo",
            "data_dir": Path("/tmp/ai-office-agents"),
        }
    )
    if isolated.mode == "demo":
        raise ValueError("Agent runtime requires an explicitly configured local model")
    provider = provider or CrewProvider(isolated)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    busy = asyncio.Lock()

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"code": exc.code}, status_code=exc.status)

    @app.get("/health")
    def health():
        available = importlib.util.find_spec("crewai") is not None
        status = provider.health() if available else "not_configured"
        return JSONResponse(
            {"status": status, "model_id": provider.model_id},
            status_code=200 if status == "ready" else 503,
        )

    @app.post("/step")
    async def step(request: Request):
        raw = await bounded_json(request, 65536)
        try:
            payload = Step.model_validate(raw)
        except ValidationError as exc:
            raise DomainError("INVALID_STEP", 422) from exc
        if busy.locked():
            raise DomainError("AGENT_RUNTIME_BUSY", 503)
        async with busy:
            try:
                output = await run_in_threadpool(
                    provider._sdk_step, payload.role, payload.instruction
                )
                if not isinstance(output, str) or len(output.encode()) > 65536:
                    raise DomainError("AGENT_RESPONSE_TOO_LARGE", 503)
                return {"output": output, "model_id": provider.model_id}
            except DomainError:
                raise
            except Exception as exc:
                # Do not expose SDK exceptions, which may contain source content.
                raise DomainError("AGENT_STEP_FAILED", 503) from exc

    return app
