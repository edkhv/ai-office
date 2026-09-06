"""Authenticated local catalog and quote workflow API."""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.auth import require
from app.contracts import DocumentACL
from app.db import rows
from app.quote_contracts import QuoteDraft, QuoteProposal, QuoteRevision, QuoteSuggestionRequest
from app.quotes import HEADERS, MAX_CATALOG_BYTES
from app.schema_v1 import tasks
from app.workflows import task_get


def make_quote_router(actor_dependency, workflows):
    router = APIRouter(prefix="/api/v1")
    service = workflows.quotes

    @router.get("/catalogs/template")
    def template(format: Literal["csv", "xlsx"] = "csv", who=Depends(actor_dependency)):
        require(who, "owner", "manager")
        data = [
            HEADERS,
            ["STEEL-01", "Demo steel / Демонстрационный металл", "pcs", "125.00", "20", "RUB"],
        ]
        if format == "xlsx":
            from openpyxl import Workbook

            workbook = Workbook()
            sheet = workbook.active
            for item in data:
                sheet.append(item)
            stream = io.BytesIO()
            workbook.save(stream)
            content = stream.getvalue()
            media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            stream = io.StringIO()
            csv.writer(stream).writerows(data)
            content = stream.getvalue().encode("utf-8-sig")
            media = "text/csv"
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="catalog-template.{format}"'},
        )

    @router.get("/catalogs")
    def list_catalogs(who=Depends(actor_dependency)):
        return service.list_catalogs(who)

    @router.post("/catalogs")
    def import_catalog(
        request: Request,
        file: UploadFile = File(),
        catalog_id: str | None = Form(None),
        who=Depends(actor_dependency),
    ):
        return service.import_catalog(
            who,
            file.filename or "",
            file.file.read(MAX_CATALOG_BYTES + 1),
            request.state.request_id,
            catalog_id,
        )

    @router.get("/catalogs/{catalog_id}/versions")
    def catalog_history(catalog_id: str, who=Depends(actor_dependency)):
        return service.list_catalog_versions(who, catalog_id)

    @router.get("/catalog-versions/{version_id}")
    def catalog_version(version_id: str, who=Depends(actor_dependency)):
        return service.catalog(who, version_id)

    @router.patch("/catalogs/{catalog_id}/acl")
    def acl(catalog_id: str, body: DocumentACL, request: Request, who=Depends(actor_dependency)):
        return service.update_catalog_acl(who, catalog_id, body, request.state.request_id)

    @router.post("/quote-suggestions", status_code=202)
    def suggest(
        body: QuoteSuggestionRequest,
        request: Request,
        idempotency_key: str = Header(),
        who=Depends(actor_dependency),
    ):
        run = workflows.submit(
            who,
            body.model_dump(mode="json"),
            idempotency_key,
            request.state.request_id,
            "quote_suggestion",
        )
        return {
            "run_id": run["id"],
            "status": run["state"],
            "status_url": f"/api/v1/runs/{run['id']}",
        }

    @router.get("/quotes")
    def list_quotes(who=Depends(actor_dependency)):
        return service.list_quotes(who)

    @router.post("/quotes", status_code=201)
    def save(body: QuoteDraft, request: Request, who=Depends(actor_dependency)):
        return service.save(who, body.model_dump(mode="json"), request.state.request_id)

    @router.get("/quotes/{quote_id}")
    def get(
        quote_id: str,
        version: int | None = Query(default=None, ge=1),
        who=Depends(actor_dependency),
    ):
        return service.get(who, quote_id, version)

    @router.patch("/quotes/{quote_id}")
    def revise(quote_id: str, body: QuoteRevision, request: Request, who=Depends(actor_dependency)):
        return service.save(
            who,
            body.model_dump(mode="json", exclude={"version"}),
            request.state.request_id,
            quote_id,
            body.version,
        )

    @router.post("/quotes/{quote_id}/propose")
    def propose(
        quote_id: str,
        body: QuoteProposal,
        request: Request,
        idempotency_key: str = Header(),
        who=Depends(actor_dependency),
    ):
        return service.propose(
            who, quote_id, body.version, idempotency_key, request.state.request_id
        )

    @router.get("/quotes/{quote_id}/tasks")
    def quote_tasks(
        quote_id: str,
        version: int | None = Query(default=None, ge=1),
        who=Depends(actor_dependency),
    ):
        quote = service.get(who, quote_id, version)
        with service.engine.connect() as conn:
            linked = rows(
                conn, select(tasks.c.id).where(tasks.c.source_run_id == quote["revision"]["run_id"])
            )
        return [task_get(service.engine, who, task["id"]) for task in linked]

    @router.get("/quotes/{quote_id}/export")
    def export(
        quote_id: str,
        format: Literal["pdf", "docx"],
        version: int | None = Query(default=None, ge=1),
        who=Depends(actor_dependency),
    ):
        content = service.export(who, quote_id, format, version)
        media = (
            "application/pdf"
            if format == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="quote.{format}"'},
        )

    return router
