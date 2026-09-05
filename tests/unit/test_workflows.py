from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.contracts import Clarification, Decision, TaskPlan
from app.db import row, transaction
from app.errors import DomainError
from app.schema_v1 import actors, approvals, jobs, proposals, tasks
from app.workflows import Workflows
from tests.conftest import COMMAND, propose


def decision(run, choice="approve"):
    p = run["proposal"]
    return Decision(decision=choice, version=p["version"], payload_hash=p["payload_hash"])


def task_count(ctx):
    with ctx["engine"].connect() as conn:
        return conn.scalar(select(func.count()).select_from(tasks))


def approve(ctx, run, choice="approve"):
    return ctx["work"].decide(ctx["actors"]["owner"], run["proposal"]["id"], decision(run, choice))


def test_full_workflow_persists_only_after_approval(ctx):
    run = propose(ctx)
    assert run["state"] == "awaiting_approval"
    assert task_count(ctx) == 0
    assert run["result"]["engine"] == "deterministic_demo"
    assert run["result"]["model_id"] is None
    approve(ctx, run)
    assert task_count(ctx) == 0
    ctx["work"].process_one()
    assert task_count(ctx) == 3
    final = ctx["work"].get(ctx["actors"]["owner"], run["id"])
    assert final["state"] == "completed"
    assert "отправ" in final["proposal"]["payload"]["proposed_messages"][0]


def test_rejection_never_executes(ctx):
    run = propose(ctx)
    approve(ctx, run, "reject")
    assert not ctx["work"].process_one()
    assert task_count(ctx) == 0


def test_repeated_approval_and_worker_are_idempotent(ctx):
    run = propose(ctx)
    approve(ctx, run)
    approve(ctx, run)
    ctx["work"].process_one()
    assert approve(ctx, run)["replayed"]
    assert not ctx["work"].process_one()
    assert task_count(ctx) == 3


def test_concurrent_approvals_create_one_execution_job(ctx):
    run = propose(ctx)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: approve(ctx, run), range(2)))
    assert sum(not r["replayed"] for r in results) == 1
    ctx["work"].process_one()
    assert task_count(ctx) == 3


def test_same_key_same_payload_returns_run(ctx):
    run = propose(ctx)
    again = ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "command-1", "test")
    assert again["id"] == run["id"]


def test_same_key_changed_payload_conflicts(ctx):
    propose(ctx)
    with pytest.raises(DomainError, match="IDEMPOTENCY_CONFLICT"):
        ctx["work"].submit(
            ctx["actors"]["owner"], {**COMMAND, "text": "Other instruction"}, "command-1", "test"
        )


@pytest.mark.parametrize("field", ["due_at", "team_id"])
def test_missing_fields_need_clarification(ctx, field):
    payload = {**COMMAND, field: None}
    run = ctx["work"].submit(ctx["actors"]["owner"], payload, field, "test")
    ctx["work"].process_one()
    result = ctx["work"].get(ctx["actors"]["owner"], run["id"])
    assert result["state"] == "needs_clarification"
    assert result["result"]["plan"]["missing_fields"]
    assert result["proposal"] is None


def test_unsupported_demo_question_is_not_fixture_success(ctx):
    run = ctx["work"].submit(
        ctx["actors"]["owner"],
        {**COMMAND, "text": "Invent a marketing campaign"},
        "unknown",
        "test",
    )
    ctx["work"].process_one()
    assert ctx["work"].get(ctx["actors"]["owner"], run["id"])["state"] == "needs_clarification"


def test_plan_revision_invalidates_approved_payload(ctx):
    run = propose(ctx)
    approve(ctx, run)
    ctx["work"].clarify(
        ctx["actors"]["owner"],
        run["id"],
        Clarification(version=1, team_id="operations", due_at="2026-09-12T16:00:00+03:00"),
    )
    with pytest.raises(DomainError, match="VERSION_CONFLICT"):
        approve(ctx, run)
    ctx["work"].process_one()
    new = ctx["work"].get(ctx["actors"]["owner"], run["id"])
    assert new["proposal"]["version"] == 2
    assert new["proposal"]["payload"]["proposed_tasks"][0]["team_id"] == "operations"
    assert task_count(ctx) == 0


def test_expired_approval_rejected(ctx):
    run = propose(ctx)
    ctx["clock"].value += 3601
    with pytest.raises(DomainError, match="APPROVAL_EXPIRED"):
        approve(ctx, run)


def test_expired_after_approval_does_not_execute(ctx):
    run = propose(ctx)
    approve(ctx, run)
    ctx["clock"].value += 3601
    ctx["work"].process_one()
    assert task_count(ctx) == 0
    assert ctx["work"].get(ctx["actors"]["owner"], run["id"])["state"] == "failed"


def test_payload_tamper_fails_at_execution(ctx):
    run = propose(ctx)
    approve(ctx, run)
    with transaction(ctx["engine"]) as conn:
        p = run["proposal"]["payload"]
        p["proposed_tasks"][0]["title"] = "Tampered task"
        conn.execute(
            proposals.update().where(proposals.c.id == run["proposal"]["id"]).values(payload=p)
        )
    ctx["work"].process_one()
    assert task_count(ctx) == 0


def test_role_revoked_after_approval(ctx):
    run = propose(ctx)
    approve(ctx, run)
    with transaction(ctx["engine"]) as conn:
        conn.execute(actors.update().where(actors.c.id == "owner").values(role="employee"))
    ctx["work"].process_one()
    assert task_count(ctx) == 0


def test_model_schema_failure_never_completes(ctx, monkeypatch):
    def invalid(*_):
        return TaskPlan(source_ref="invented", proposed_tasks=[])

    monkeypatch.setattr(ctx["work"].provider, "plan", invalid)
    run = propose(ctx)
    assert run["state"] == "failed"
    assert task_count(ctx) == 0


def test_claim_recovers_after_worker_restart(ctx):
    run = ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "restart", "test")
    abandoned = ctx["work"].claim()
    ctx["clock"].value += 301
    restarted = Workflows(
        ctx["engine"], ctx["settings"], ctx["work"].provider, ctx["knowledge"], ctx["clock"]
    )
    assert restarted.process_one()
    assert restarted.get(ctx["actors"]["owner"], run["id"])["state"] == "awaiting_approval"
    with ctx["engine"].connect() as conn:
        job = row(conn, select(jobs).where(jobs.c.id == abandoned["id"]))
        assert job["attempts"] == 2


def test_crash_mid_transaction_rolls_back_then_restart_executes_once(ctx, monkeypatch):
    import app.workflows as module

    run = propose(ctx)
    approve(ctx, run)
    original = module.record

    def crash(conn, actor, action, target, outcome, *args, **kwargs):
        if action == "create_local_tasks" and outcome == "succeeded":
            raise KeyboardInterrupt("simulated process crash before commit")
        return original(conn, actor, action, target, outcome, *args, **kwargs)

    monkeypatch.setattr(module, "record", crash)
    with pytest.raises(KeyboardInterrupt):
        ctx["work"].process_one()
    assert task_count(ctx) == 0
    ctx["clock"].value += 301
    monkeypatch.setattr(module, "record", original)
    ctx["work"].process_one()
    assert task_count(ctx) == 3
    with ctx["engine"].connect() as conn:
        assert conn.scalar(select(approvals.c.executed_at)) is not None


def test_stale_worker_cannot_commit_after_lease_reclaimed(ctx):
    ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "lease", "test")
    first = ctx["work"].claim()
    ctx["clock"].value += 301
    second = ctx["work"].claim()
    with ctx["engine"].connect() as conn:
        assert not ctx["work"].lease_valid(conn, first)
        assert ctx["work"].lease_valid(conn, second)


def test_queue_bound(ctx):
    ctx["settings"].max_queue = 1
    ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "one", "test")
    with pytest.raises(DomainError, match="QUEUE_FULL"):
        ctx["work"].submit(ctx["actors"]["owner"], COMMAND, "two", "test")
