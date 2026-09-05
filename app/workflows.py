import time
from datetime import UTC

from sqlalchemy import and_, func, or_, select

from app.auth import get_actor, require
from app.contracts import Command, TaskPlan
from app.db import digest, record, row, rows, transaction, uid
from app.errors import DomainError
from app.providers import validate_plan
from app.schema_v1 import approvals, jobs, proposals, runs, tasks


def enqueue(conn, run_id, stage):
    conn.execute(
        jobs.insert().values(
            id=uid(),
            run_id=run_id,
            stage=stage,
            status="queued",
            attempts=0,
            lease_until=0,
            next_attempt_at=0,
        )
    )


def authorized_run(conn, actor, run_id):
    run = row(
        conn,
        select(runs).where(
            runs.c.id == run_id,
            runs.c.organization_id == actor.organization_id,
            runs.c.actor_id == actor.id,
        ),
    )
    if not run:
        raise DomainError("NOT_FOUND", 404)
    return run


class Workflows:
    def __init__(self, engine, settings, provider, knowledge, clock=time.time):
        self.engine, self.settings = engine, settings
        self.provider, self.knowledge, self.clock = provider, knowledge, clock

    def submit(self, actor, payload, key, correlation_id, kind="command"):
        if kind == "command":
            require(actor, "owner", "manager")
        if not key or len(key) > 100:
            raise DomainError("IDEMPOTENCY_KEY_REQUIRED", 422)
        now = self.clock()
        with transaction(self.engine) as conn:
            previous = row(
                conn, select(runs).where(runs.c.actor_id == actor.id, runs.c.idempotency_key == key)
            )
            hashed = digest({"kind": kind, "payload": payload})
            if previous:
                if previous["input_hash"] != hashed:
                    raise DomainError("IDEMPOTENCY_CONFLICT", 409)
                return previous
            queued = conn.scalar(
                select(func.count())
                .select_from(jobs)
                .where(jobs.c.status.in_(["queued", "running"]))
            )
            if queued >= self.settings.max_queue:
                raise DomainError("QUEUE_FULL", 503, retryable=True)
            run_id = uid()
            values = dict(
                id=run_id,
                organization_id=actor.organization_id,
                actor_id=actor.id,
                type=kind,
                state="received",
                version=1,
                input=payload,
                created_at=now,
                updated_at=now,
                correlation_id=correlation_id,
                idempotency_key=key,
                input_hash=hashed,
            )
            conn.execute(runs.insert().values(**values))
            enqueue(conn, run_id, "plan:1" if kind == "command" else "answer:1")
            record(
                conn,
                actor,
                "command_received" if kind == "command" else "question_received",
                run_id,
                "succeeded",
                correlation_id,
                now=now,
            )
            return values

    def get(self, actor, run_id):
        with self.engine.connect() as conn:
            run = authorized_run(conn, actor, run_id)
            run["proposal"] = row(
                conn,
                select(proposals).where(
                    proposals.c.run_id == run_id, proposals.c.version == run["version"]
                ),
            )
            run["jobs"] = rows(conn, select(jobs).where(jobs.c.run_id == run_id))
        if run["type"] == "answer" and run.get("result") and "evidence" in run["result"]:
            # Current ACL checks apply to persisted answers too, including old browser links.
            evidence = run["result"]["evidence"]
            if not all(self.knowledge.evidence_allowed(actor, e) for e in evidence):
                run["result"] = {
                    "status": "evidence_revoked",
                    "answer": "Source access changed. Ask again.",
                }
        return run

    def clarify(self, actor, run_id, clarification):
        require(actor, "owner", "manager")
        with transaction(self.engine) as conn:
            run = authorized_run(conn, actor, run_id)
            if run["version"] != clarification.version or run["state"] not in {
                "needs_clarification",
                "awaiting_approval",
                "approved",
            }:
                raise DomainError("VERSION_CONFLICT", 409)
            command = Command.model_validate(run["input"])
            command.team_id, command.due_at = clarification.team_id, clarification.due_at
            version = run["version"] + 1
            conn.execute(
                proposals.update().where(proposals.c.run_id == run_id).values(status="superseded")
            )
            conn.execute(
                jobs.update()
                .where(jobs.c.run_id == run_id, jobs.c.status.in_(["queued", "running"]))
                .values(status="cancelled", lease_token=None)
            )
            conn.execute(
                runs.update()
                .where(runs.c.id == run_id)
                .values(
                    input=command.model_dump(mode="json"),
                    version=version,
                    state="received",
                    result=None,
                    updated_at=self.clock(),
                )
            )
            enqueue(conn, run_id, f"plan:{version}")
            record(
                conn,
                actor,
                "plan_revised",
                run_id,
                "proposed",
                run["correlation_id"],
                {"version": version},
                now=self.clock(),
            )
        return self.get(actor, run_id)

    def decide(self, actor, proposal_id, decision):
        require(actor, "owner", "manager")
        now = self.clock()
        with transaction(self.engine) as conn:
            proposal = row(conn, select(proposals).where(proposals.c.id == proposal_id))
            if not proposal:
                raise DomainError("NOT_FOUND", 404)
            run = authorized_run(conn, actor, proposal["run_id"])
            if (
                proposal["version"] != decision.version
                or proposal["version"] != run["version"]
                or proposal["payload_hash"] != decision.payload_hash
                or digest(proposal["payload"]) != decision.payload_hash
            ):
                raise DomainError("VERSION_CONFLICT", 409)
            existing = row(conn, select(approvals).where(approvals.c.proposal_id == proposal_id))
            if existing:
                if existing["decision"] != decision.decision:
                    raise DomainError("DECISION_CONFLICT", 409)
                return {"run_id": run["id"], "state": run["state"], "replayed": True}
            if proposal["expires_at"] <= now:
                raise DomainError("APPROVAL_EXPIRED", 409)
            if proposal["status"] != "pending" or run["state"] != "awaiting_approval":
                raise DomainError("INVALID_STATE", 409)
            state = "approved" if decision.decision == "approve" else "rejected"
            conn.execute(
                approvals.insert().values(
                    id=uid(),
                    proposal_id=proposal_id,
                    actor_id=actor.id,
                    decision=decision.decision,
                    payload_hash=decision.payload_hash,
                    expires_at=proposal["expires_at"],
                )
            )
            conn.execute(
                proposals.update().where(proposals.c.id == proposal_id).values(status=state)
            )
            conn.execute(
                runs.update().where(runs.c.id == run["id"]).values(state=state, updated_at=now)
            )
            if state == "approved":
                enqueue(conn, run["id"], f"execute:{run['version']}")
            record(
                conn,
                actor,
                "approval_decision",
                proposal_id,
                state,
                run["correlation_id"],
                {"version": decision.version, "payload_hash": decision.payload_hash},
                now=now,
            )
        return {"run_id": run["id"], "state": state, "replayed": False}

    def claim(self):
        now = self.clock()
        with transaction(self.engine) as conn:
            job = row(
                conn,
                select(jobs)
                .where(
                    or_(
                        and_(jobs.c.status == "queued", jobs.c.next_attempt_at <= now),
                        and_(jobs.c.status == "running", jobs.c.lease_until < now),
                    )
                )
                .order_by(jobs.c.next_attempt_at, jobs.c.id)
                .limit(1),
            )
            if not job:
                return None
            token = uid()
            conn.execute(
                jobs.update()
                .where(jobs.c.id == job["id"])
                .values(
                    status="running",
                    attempts=job["attempts"] + 1,
                    lease_until=now + self.settings.lease_seconds,
                    lease_token=token,
                )
            )
            run = row(conn, select(runs).where(runs.c.id == job["run_id"]))
            state = "executing" if job["stage"].startswith("execute:") else "planning"
            conn.execute(
                runs.update().where(runs.c.id == run["id"]).values(state=state, updated_at=now)
            )
            return {**job, "lease_token": token, "attempts": job["attempts"] + 1}

    def lease_valid(self, conn, job):
        current = row(
            conn,
            select(jobs).where(
                jobs.c.id == job["id"],
                jobs.c.status == "running",
                jobs.c.lease_token == job["lease_token"],
                jobs.c.lease_until > self.clock(),
            ),
        )
        return bool(current)

    def process_one(self):
        job = self.claim()
        if not job:
            return False
        try:
            with self.engine.connect() as conn:
                run = row(conn, select(runs).where(runs.c.id == job["run_id"]))
                actor = get_actor(conn, run["actor_id"])
            if job["stage"].startswith("execute:"):
                self.execute(job)
                return True
            if job["attempts"] > 3:
                raise DomainError("JOB_RETRY_LIMIT", 503)
            if run["type"] == "command":
                require(actor, "owner", "manager")
                command = Command.model_validate(run["input"])
                plan = validate_plan(self.provider.plan(command, run["id"]), command, run["id"])
                result = {
                    "plan": plan.model_dump(mode="json"),
                    "engine": self.provider.engine,
                    "model_id": self.provider.model_id,
                }
                state = "needs_clarification" if plan.missing_fields else "awaiting_approval"
            else:
                evidence = self.knowledge.search(actor, run["input"]["query"])
                answer = self.provider.answer(run["input"]["query"], evidence)
                result = {
                    **answer.model_dump(),
                    "evidence": evidence,
                    "engine": self.provider.engine,
                    "model_id": self.provider.model_id,
                    "status": "insufficient_evidence"
                    if answer.insufficient_evidence
                    else "answered",
                }
                state = "completed"
            with transaction(self.engine) as conn:
                if not self.lease_valid(conn, job):
                    return True
                current_actor = get_actor(conn, actor.id)
                if run["type"] == "command":
                    require(current_actor, "owner", "manager")
                if run["type"] == "answer" and not all(
                    self.knowledge.evidence_allowed(current_actor, e, conn=conn)
                    for e in result["evidence"]
                ):
                    raise DomainError("EVIDENCE_ACCESS_CHANGED", 409)
                if state == "awaiting_approval":
                    payload = result["plan"]
                    conn.execute(
                        proposals.insert().values(
                            id=uid(),
                            run_id=run["id"],
                            version=run["version"],
                            payload=payload,
                            payload_hash=digest(payload),
                            expires_at=self.clock() + 3600,
                            status="pending",
                        )
                    )
                conn.execute(
                    runs.update()
                    .where(runs.c.id == run["id"])
                    .values(state=state, result=result, updated_at=self.clock())
                )
                conn.execute(
                    jobs.update()
                    .where(jobs.c.id == job["id"])
                    .values(status="done", lease_token=None)
                )
                record(
                    conn,
                    current_actor,
                    "plan_prepared" if run["type"] == "command" else "answer_prepared",
                    run["id"],
                    "proposed" if run["type"] == "command" else "succeeded",
                    run["correlation_id"],
                    {"state": state, "engine": self.provider.engine},
                    now=self.clock(),
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, DomainError) else "JOB_FAILED"
            with transaction(self.engine) as conn:
                if self.lease_valid(conn, job):
                    run = row(conn, select(runs).where(runs.c.id == job["run_id"]))
                    conn.execute(
                        jobs.update()
                        .where(jobs.c.id == job["id"])
                        .values(status="failed", error_code=code, lease_token=None)
                    )
                    conn.execute(
                        runs.update()
                        .where(runs.c.id == run["id"])
                        .values(
                            state="failed", result={"error_code": code}, updated_at=self.clock()
                        )
                    )
                    # Preserve revoked actor identity in audit without granting permissions.
                    from app.contracts import Actor

                    identity = Actor(
                        id=run["actor_id"],
                        organization_id=run["organization_id"],
                        role="employee",
                        team_id="operations",
                    )
                    record(
                        conn,
                        identity,
                        "job",
                        job["id"],
                        "failed",
                        run["correlation_id"],
                        {"error_code": code},
                        now=self.clock(),
                    )
        return True

    def execute(self, job):
        with transaction(self.engine) as conn:
            if not self.lease_valid(conn, job):
                return
            run = row(conn, select(runs).where(runs.c.id == job["run_id"]))
            actor = get_actor(conn, run["actor_id"])
            require(actor, "owner", "manager")
            proposal = row(
                conn,
                select(proposals).where(
                    proposals.c.run_id == run["id"],
                    proposals.c.version == run["version"],
                    proposals.c.status == "approved",
                ),
            )
            if not proposal:
                raise DomainError("APPROVAL_REQUIRED", 409)
            approval = row(
                conn,
                select(approvals).where(
                    approvals.c.proposal_id == proposal["id"], approvals.c.decision == "approve"
                ),
            )
            if (
                not approval
                or approval["actor_id"] != actor.id
                or approval["expires_at"] <= self.clock()
            ):
                raise DomainError("APPROVAL_EXPIRED_OR_REVOKED", 409)
            require(get_actor(conn, approval["actor_id"]), "owner", "manager")
            if digest(proposal["payload"]) != approval["payload_hash"]:
                raise DomainError("PAYLOAD_CHANGED", 409)
            plan = validate_plan(
                TaskPlan.model_validate(proposal["payload"]),
                Command.model_validate(run["input"]),
                run["id"],
            )
            record(
                conn,
                actor,
                "create_local_tasks",
                run["id"],
                "attempted",
                run["correlation_id"],
                now=self.clock(),
            )
            for slot, task in enumerate(plan.proposed_tasks):
                conn.execute(
                    tasks.insert().values(
                        id=uid(),
                        organization_id=actor.organization_id,
                        title=task.title,
                        team_id=task.team_id,
                        due_at=task.due_at.astimezone(UTC).isoformat(),
                        acceptance_criteria=task.acceptance_criteria,
                        status="todo",
                        result="",
                        source_run_id=run["id"],
                        slot=slot,
                    )
                )
            conn.execute(
                approvals.update()
                .where(approvals.c.id == approval["id"])
                .values(executed_at=self.clock())
            )
            conn.execute(
                proposals.update().where(proposals.c.id == proposal["id"]).values(status="executed")
            )
            conn.execute(
                runs.update()
                .where(runs.c.id == run["id"])
                .values(state="completed", updated_at=self.clock())
            )
            conn.execute(
                jobs.update().where(jobs.c.id == job["id"]).values(status="done", lease_token=None)
            )
            record(
                conn,
                actor,
                "create_local_tasks",
                run["id"],
                "succeeded",
                run["correlation_id"],
                {"task_count": len(plan.proposed_tasks)},
                now=self.clock(),
            )


def task_scope(actor):
    scope = tasks.c.organization_id == actor.organization_id
    if actor.role == "employee":
        scope = and_(scope, tasks.c.team_id == actor.team_id)
    return scope


def task_list(engine, actor, limit=50, offset=0):
    with engine.connect() as conn:
        return rows(
            conn,
            select(tasks)
            .where(task_scope(actor))
            .order_by(tasks.c.due_at, tasks.c.id)
            .limit(limit)
            .offset(offset),
        )


def update_task(engine, actor, task_id, update, correlation_id, now):
    with transaction(engine) as conn:
        task = row(conn, select(tasks).where(tasks.c.id == task_id, task_scope(actor)))
        if not task:
            raise DomainError("NOT_FOUND", 404)
        conn.execute(tasks.update().where(tasks.c.id == task_id).values(**update.model_dump()))
        record(
            conn,
            actor,
            "task_status",
            task_id,
            "succeeded",
            correlation_id,
            {"before": task["status"], "after": update.status},
            now=now,
        )
    return {"id": task_id, **update.model_dump()}
