import json
import logging
import time
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from starlette.exceptions import HTTPException

from app import auth, services
from app.config import Settings
from app.contracts import Clarification, Command, Decision, DocumentACL, Login, TaskUpdate
from app.contracts import Query as SearchQuery
from app.db import engine_for, row, rows, transaction, uid
from app.errors import DomainError
from app.knowledge import Knowledge
from app.providers import provider_for
from app.schema_v1 import audit, heartbeats, runs, sessions
from app.workflows import Workflows, task_list, update_task


def create_app(settings=None, engine=None, provider=None, knowledge=None, clock=time.time):
    settings = settings or Settings()
    engine = engine or engine_for(settings)
    provider = provider or provider_for(settings)
    knowledge = knowledge or Knowledge(engine, settings, clock=clock)
    workflows = Workflows(engine, settings, provider, knowledge, clock)
    app = FastAPI(
        title="AI Office", version="0.1.0-alpha", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.engine, app.state.settings = engine, settings
    app.state.workflows, app.state.knowledge = workflows, knowledge
    template_root = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=template_root / "static"), name="static")
    templates = Jinja2Templates(directory=template_root / "templates")

    def error_response(request, code, status, message=None, retryable=False):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message or code.replace("_", " ").capitalize(),
                    "request_id": getattr(request.state, "request_id", uid()),
                    "retryable": retryable,
                }
            },
        )

    @app.middleware("http")
    async def boundary(request, call_next):
        request.state.request_id = uid()
        start = time.monotonic()
        try:
            # Bound streamed bodies as well as Content-Length; uploads include multipart overhead.
            if request.method in {"POST", "PATCH", "PUT"}:
                body = bytearray()
                async for part in request.stream():
                    body.extend(part)
                    if len(body) > settings.max_upload_bytes + 16384:
                        raise DomainError("REQUEST_TOO_LARGE", 413)
                request._body = bytes(body)
            response = await call_next(request)
        except DomainError as exc:
            response = error_response(request, exc.code, exc.status, exc.message, exc.retryable)
        except Exception:
            response = error_response(request, "INTERNAL_ERROR", 500)
        response.headers.update(
            {
                "X-Request-ID": request.state.request_id,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            }
        )
        logging.getLogger("ai-office").info(
            json.dumps(
                {
                    "event": "http",
                    "method": request.method,
                    "status": response.status_code,
                    "request_id": request.state.request_id,
                    "latency_ms": round((time.monotonic() - start) * 1000),
                }
            )
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error_response(request, exc.code, exc.status, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo credential/input values from Pydantic error details.
        return error_response(
            request, "VALIDATION_ERROR", 422, "Request fields are invalid or missing."
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(request, "HTTP_ERROR", exc.status_code)

    def actor(request: Request):
        bearer = request.headers.get("Authorization", "")
        if bearer.startswith("Bearer "):
            return auth.authenticate(engine, bearer[7:], clock())
        token = request.cookies.get("office_session")
        if not token:
            raise DomainError("UNAUTHORIZED", 401)
        return auth.authenticate(
            engine,
            token,
            clock(),
            cookie=True,
            csrf=request.headers.get("X-CSRF-Token"),
            mutation=request.method not in {"GET", "HEAD", "OPTIONS"},
        )

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/health/live")
    def live():
        return {"status": "alive"}

    def checks():
        result = {
            "database": False,
            "qdrant": False,
            "worker": False,
            "provider": provider.health() == "ready",
        }
        try:
            with engine.connect() as conn:
                conn.execute(select(runs.c.id).limit(1))
                result["database"] = True
                beat = row(conn, select(heartbeats).where(heartbeats.c.id == "worker"))
                result["worker"] = bool(
                    beat and beat["seen_at"] > clock() - settings.lease_seconds - 30
                )
            knowledge.ensure_store()
            knowledge.client.get_collection(knowledge.index_name)
            result["qdrant"] = True
        except Exception:
            pass
        return result

    @app.get("/health/ready")
    def ready():
        ok = all(checks().values())
        return JSONResponse(
            {"status": "ready" if ok else "degraded"}, status_code=200 if ok else 503
        )

    @app.post("/api/v1/auth/login")
    def login(body: Login, request: Request):
        origin = request.headers.get("Origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise DomainError("CSRF_REJECTED", 403)
        who, token, csrf = auth.login(
            engine,
            settings,
            body.token,
            request.client.host if request.client else "local",
            clock(),
            request.state.request_id,
        )
        response = JSONResponse({"actor": who.model_dump(), "csrf_token": csrf})
        response.set_cookie(
            "office_session",
            token,
            max_age=settings.session_seconds,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
        )
        response.set_cookie(
            "office_csrf",
            csrf,
            max_age=settings.session_seconds,
            secure=settings.cookie_secure,
            samesite="strict",
        )
        return response

    @app.get("/api/v1/auth/me")
    def me(who=Depends(actor)):
        return who.model_dump()

    @app.post("/api/v1/auth/logout")
    def logout(request: Request, who=Depends(actor)):
        with transaction(engine) as conn:
            conn.execute(
                sessions.delete().where(
                    sessions.c.digest == auth.digest(request.cookies.get("office_session", ""))
                )
            )
        response = JSONResponse({"status": "logged_out"})
        response.delete_cookie("office_session")
        response.delete_cookie("office_csrf")
        return response

    @app.get("/api/v1/openapi.json")
    def openapi(who=Depends(actor)):
        return app.openapi()

    @app.get("/api/v1/system/capabilities")
    def capabilities(who=Depends(actor)):
        entries = json.loads((template_root / "capabilities.json").read_text())
        return {
            "mode": settings.mode,
            "engine": provider.engine,
            "model_id": provider.model_id,
            "synthetic_data": True,
            "provider_status": provider.health(),
            "checks": checks(),
            "hardware": {
                "target": "Orange Pi AI Studio Pro 96 GB",
                "status": "hardware_validation_pending",
                "implementation": "partial",
                "validation": "not_run",
                "message": "Target hardware; not yet validated on device.",
            },
            "external_actions": "not_implemented",
            "capabilities": entries,
            "embedding_mode": settings.embedding_provider,
            "warning": "Lexical/hash embeddings and deterministic fixture responses"
            if settings.mode == "demo"
            else "Local model output requires verification; synthetic business records",
        }

    @app.post("/api/v1/commands", status_code=202)
    def command(
        body: Command, request: Request, idempotency_key: str = Header(), who=Depends(actor)
    ):
        run = workflows.submit(
            who, body.model_dump(mode="json"), idempotency_key, request.state.request_id
        )
        return {
            "run_id": run["id"],
            "status": run["state"],
            "mode": settings.mode,
            "status_url": f"/api/v1/runs/{run['id']}",
        }

    @app.get("/api/v1/runs")
    def list_runs(
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        who=Depends(actor),
    ):
        with engine.connect() as conn:
            return rows(
                conn,
                select(runs.c.id, runs.c.type, runs.c.state, runs.c.created_at)
                .where(runs.c.actor_id == who.id, runs.c.organization_id == who.organization_id)
                .order_by(runs.c.created_at.desc())
                .limit(limit)
                .offset(offset),
            )

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str, who=Depends(actor)):
        return workflows.get(who, run_id)

    @app.post("/api/v1/runs/{run_id}/clarifications")
    def clarify(run_id: str, body: Clarification, who=Depends(actor)):
        return workflows.clarify(who, run_id, body)

    @app.post("/api/v1/approvals/{proposal_id}/decision")
    def decide(proposal_id: str, body: Decision, who=Depends(actor)):
        return workflows.decide(who, proposal_id, body)

    @app.get("/api/v1/tasks")
    def get_tasks(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        who=Depends(actor),
    ):
        return task_list(engine, who, limit, offset)

    @app.patch("/api/v1/tasks/{task_id}")
    def patch_task(task_id: str, body: TaskUpdate, request: Request, who=Depends(actor)):
        return update_task(engine, who, task_id, body, request.state.request_id, clock())

    @app.post("/api/v1/documents")
    def upload(
        request: Request,
        file: UploadFile = File(),
        roles: str = Form("owner,manager,employee"),
        document_id: str | None = Form(None),
        who=Depends(actor),
    ):
        return knowledge.import_document(
            who,
            file.filename or "",
            file.file.read(settings.max_upload_bytes + 1),
            roles.split(","),
            request.state.request_id,
            document_id,
            file.content_type or "application/octet-stream",
        )

    @app.get("/api/v1/documents")
    def get_documents(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        who=Depends(actor),
    ):
        return knowledge.list_documents(who, limit, offset)

    @app.get("/api/v1/documents/{document_id}")
    def get_document(
        document_id: str, version: int | None = Query(default=None, ge=1), who=Depends(actor)
    ):
        doc = knowledge.get_document(who, document_id)
        return knowledge.get_document(who, document_id, version or doc["current_version"])

    @app.patch("/api/v1/documents/{document_id}/acl")
    def acl(document_id: str, body: DocumentACL, request: Request, who=Depends(actor)):
        return knowledge.update_acl(who, document_id, body, request.state.request_id)

    @app.post("/api/v1/knowledge/search")
    def search(body: SearchQuery, who=Depends(actor)):
        evidence = knowledge.search(who, body.query)
        return {"status": "found" if evidence else "insufficient_evidence", "evidence": evidence}

    @app.post("/api/v1/knowledge/ask", status_code=202)
    def ask(
        body: SearchQuery, request: Request, idempotency_key: str = Header(), who=Depends(actor)
    ):
        run = workflows.submit(
            who, body.model_dump(), idempotency_key, request.state.request_id, "answer"
        )
        return {
            "run_id": run["id"],
            "status": run["state"],
            "status_url": f"/api/v1/runs/{run['id']}",
        }

    @app.get("/api/v1/metrics")
    def get_metrics(who=Depends(actor)):
        return services.metrics(engine, who, clock())

    @app.get("/api/v1/metrics/{metric_id}/lineage")
    def get_lineage(metric_id: str, who=Depends(actor)):
        return services.lineage(engine, who, metric_id, clock())

    @app.post("/api/v1/briefings")
    def create_briefing(request: Request, who=Depends(actor)):
        return services.briefing(engine, who, clock(), request.state.request_id)

    @app.get("/api/v1/audit")
    def get_audit(
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        who=Depends(actor),
    ):
        auth.require(who, "owner", "manager")
        scope = audit.c.organization_id == who.organization_id
        if who.role == "manager":
            scope = scope & (audit.c.actor_id == who.id)
        with engine.connect() as conn:
            return rows(
                conn,
                select(audit)
                .where(scope)
                .order_by(audit.c.timestamp.desc(), audit.c.id)
                .limit(limit)
                .offset(offset),
            )

    return app
