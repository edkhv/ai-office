import pytest

from app.db import transaction
from app.schema_v1 import credentials, tasks
from tests.conftest import COMMAND, headers, propose
from tests.unit.test_workflows import approve


@pytest.mark.parametrize(
    "path",
    [
        "/tasks",
        "/metrics",
        "/documents",
        "/audit",
        "/runs",
        "/system/capabilities",
        "/openapi.json",
    ],
)
def test_business_requires_auth(ctx, path):
    assert ctx["client"].get("/api/v1" + path).status_code == 401


def test_client_cannot_select_actor_or_role(ctx, owner_headers):
    response = ctx["client"].post(
        "/api/v1/commands",
        headers={**owner_headers, "Idempotency-Key": "bad-role"},
        json={**COMMAND, "role": "owner", "actor_id": "manager"},
    )
    assert response.status_code == 422


def test_employee_cannot_submit_or_read_metrics(ctx, employee_headers):
    assert (
        ctx["client"]
        .post(
            "/api/v1/commands", headers={**employee_headers, "Idempotency-Key": "bad"}, json=COMMAND
        )
        .status_code
        == 403
    )
    assert ctx["client"].get("/api/v1/metrics", headers=employee_headers).status_code == 403
    assert ctx["client"].post("/api/v1/briefings", headers=employee_headers).status_code == 403


def test_run_id_and_approval_id_do_not_grant_access(ctx, employee_headers):
    run = propose(ctx)
    assert (
        ctx["client"].get("/api/v1/runs/" + run["id"], headers=employee_headers).status_code == 404
    )
    assert (
        ctx["client"].get("/api/v1/runs/" + run["id"], headers=headers(ctx, "manager")).status_code
        == 404
    )
    response = ctx["client"].post(
        "/api/v1/approvals/" + run["proposal"]["id"] + "/decision",
        headers=headers(ctx, "manager"),
        json={"decision": "approve", "version": 1, "payload_hash": run["proposal"]["payload_hash"]},
    )
    assert response.status_code == 404


def test_cookie_csrf_logout_and_revocation(ctx):
    c = ctx["client"]
    token = (ctx["settings"].data_dir / "owner.token").read_text().strip()
    login = c.post("/api/v1/auth/login", json={"token": token})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]
    assert c.get("/api/v1/tasks").status_code == 200
    assert c.post("/api/v1/briefings").status_code == 403
    csrf = login.json()["csrf_token"]
    assert c.post("/api/v1/briefings", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert c.get("/api/v1/tasks").status_code == 401


def test_login_origin_rejected(ctx):
    token = (ctx["settings"].data_dir / "owner.token").read_text().strip()
    assert (
        ctx["client"]
        .post(
            "/api/v1/auth/login", headers={"Origin": "https://evil.invalid"}, json={"token": token}
        )
        .status_code
        == 403
    )


def test_expired_and_revoked_credential_invalidates_session(ctx, owner_headers):
    token = (ctx["settings"].data_dir / "owner.token").read_text().strip()
    assert ctx["client"].post("/api/v1/auth/login", json={"token": token}).status_code == 200
    with transaction(ctx["engine"]) as conn:
        conn.execute(
            credentials.update().where(credentials.c.actor_id == "owner").values(revoked=True)
        )
    assert ctx["client"].get("/api/v1/tasks").status_code == 401
    assert ctx["client"].get("/api/v1/tasks", headers=owner_headers).status_code == 401


def test_session_expiration(ctx):
    token = (ctx["settings"].data_dir / "owner.token").read_text().strip()
    ctx["client"].post("/api/v1/auth/login", json={"token": token})
    ctx["clock"].value += 28801
    assert ctx["client"].get("/api/v1/tasks").status_code == 401


def test_login_rate_limit_and_safe_error(ctx):
    token = "fake-sensitive-value-123456789"
    for _ in range(10):
        r = ctx["client"].post("/api/v1/auth/login", json={"token": token})
        assert r.status_code == 401
        assert token not in r.text
    assert ctx["client"].post("/api/v1/auth/login", json={"token": token}).status_code == 429
    ctx["clock"].value += 61
    assert ctx["client"].post("/api/v1/auth/login", json={"token": token}).status_code == 401


def test_task_team_scope_enforced(ctx, employee_headers):
    run = propose(ctx)
    approve(ctx, run)
    ctx["work"].process_one()
    visible = ctx["client"].get("/api/v1/tasks", headers=employee_headers).json()
    assert len(visible) == 3
    task_id = visible[0]["id"]
    assert (
        ctx["client"]
        .patch(
            "/api/v1/tasks/" + task_id,
            headers=employee_headers,
            json={"status": "done", "result": "Comparison prepared"},
        )
        .status_code
        == 200
    )
    with transaction(ctx["engine"]) as conn:
        conn.execute(tasks.update().where(tasks.c.id == task_id).values(team_id="operations"))
    assert (
        ctx["client"]
        .patch("/api/v1/tasks/" + task_id, headers=employee_headers, json={"status": "done"})
        .status_code
        == 404
    )


def test_health_safe_headers_and_degraded_worker(ctx):
    c = ctx["client"]
    r = c.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    ctx["clock"].value += 400
    assert c.get("/health/ready").status_code == 503
    assert c.get("/health/live").status_code == 200


def test_no_sensitive_request_contents_in_logs(ctx, owner_headers, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="ai-office")
    text = "PRIVATE_INSTRUCTION_MARKER steel offers"
    ctx["client"].post(
        "/api/v1/commands",
        headers={**owner_headers, "Idempotency-Key": "private"},
        json={**COMMAND, "text": text},
    )
    assert text not in caplog.text
    assert owner_headers["Authorization"][7:] not in caplog.text
    assert "request_id" in caplog.text


def test_hardware_never_reported_ready(ctx, owner_headers):
    c = ctx["client"].get("/api/v1/system/capabilities", headers=owner_headers).json()
    assert c["hardware"]["status"] == "hardware_validation_pending"
    assert c["hardware"]["validation"] == "not_run"


def test_pagination_bounds_and_request_limit(ctx, owner_headers):
    assert ctx["client"].get("/api/v1/tasks?limit=10000", headers=owner_headers).status_code == 422
    assert (
        ctx["client"]
        .post("/api/v1/commands", headers=owner_headers, content=b"x" * 160000)
        .status_code
        == 413
    )


def test_xss_kept_as_text_and_ui_uses_safe_dom(ctx, owner_headers):
    from pathlib import Path

    r = ctx["client"].post(
        "/api/v1/documents",
        headers=owner_headers,
        files={"file": ("xss.md", b"<script>alert(1)</script>", "text/markdown")},
    )
    assert r.status_code == 200
    d = ctx["client"].get("/api/v1/documents/" + r.json()["document_id"], headers=owner_headers)
    assert "<script>" in d.json()["content"]
    assert d.headers["content-type"].startswith("application/json")
    assert "innerHTML" not in Path("app/static/app.js").read_text()
