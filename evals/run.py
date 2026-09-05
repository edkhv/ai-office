"""Deterministic business evals against the real services, SQL and embedded Qdrant."""

import json
import socket
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from sqlalchemy import func, select

from app.auth import get_actor
from app.config import Settings
from app.contracts import Decision
from app.db import engine_for, migrate
from app.errors import DomainError
from app.knowledge import Knowledge
from app.main import create_app
from app.schema_v1 import tasks
from app.services import seed


def main():
    Path(".runtime").mkdir(exist_ok=True, mode=0o700)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_sha": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        or None,
        "config": "demo",
        "fixture_version": "northline-v1",
        "engine": "deterministic_demo",
        "model_id": None,
        "tokens": None,
        "cost": None,
        "llm_quality": "not_measured",
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "cases": [],
    }
    original = socket.socket.connect

    def deny(*args, **kwargs):
        raise AssertionError("Demo eval attempted network egress")

    socket.socket.connect = deny
    with tempfile.TemporaryDirectory(dir=".runtime") as tmp:
        s = Settings(data_dir=Path(tmp), _env_file=None)
        migrate(s)
        engine = engine_for(s)
        k = Knowledge(engine, s, client=QdrantClient(":memory:"))

        def now():
            return datetime.fromisoformat("2026-09-07T09:00:00+03:00").timestamp()

        seed(engine, s, k, now())
        app = create_app(s, engine, knowledge=k, clock=now)
        work = app.state.workflows
        with engine.connect() as conn:
            owner = get_actor(conn, "owner")

        def count():
            with engine.connect() as conn:
                return conn.scalar(select(func.count()).select_from(tasks))

        with TestClient(app) as client:
            owner_headers = {
                "Authorization": "Bearer " + (s.data_dir / "owner.token").read_text().strip()
            }
            employee_headers = {
                "Authorization": "Bearer " + (s.data_dir / "employee.token").read_text().strip()
            }
            for file in sorted(Path("evals/cases").glob("*.yaml")):
                case = yaml.safe_load(file.read_text())
                started = time.monotonic()
                outcome = {"id": case["id"], "critical": case["critical"]}
                try:
                    if case["suite"] == "workflow_safety":
                        cmd = json.loads(Path(case["input_fixture"]).read_text())
                        run = work.submit(owner, cmd, "eval-approval", "eval")
                        before = count()
                        work.process_one()
                        run = work.get(owner, run["id"])
                        expected = case["expected"]
                        assert run["state"] == expected["state_before_approval"]
                        assert count() - before == expected["tasks_created_before_approval"]
                        p = run["proposal"]
                        d = Decision(
                            decision="approve", version=p["version"], payload_hash=p["payload_hash"]
                        )
                        work.decide(owner, p["id"], d)
                        work.process_one()
                        after = count()
                        assert after - before == expected["tasks_created_after_approval"]
                        work.decide(owner, p["id"], d)
                        work.process_one()
                        assert (
                            count() - after == expected["duplicate_tasks_after_repeated_approval"]
                        )
                        outcome["actual"] = {
                            "state_before_approval": run["state"],
                            "tasks_created": after - before,
                            "duplicates": count() - after,
                        }
                    elif case["suite"] == "evidence_safety":
                        docs = client.get("/api/v1/documents", headers=owner_headers).json()
                        private = next(d for d in docs if d["name"] == "restricted.txt")
                        found = client.post(
                            "/api/v1/knowledge/search",
                            headers=employee_headers,
                            json={"query": "OWNER_EVIDENCE_7391"},
                        ).json()["evidence"]
                        leaked = sum(e["source_id"] == private["id"] for e in found)
                        direct = client.get(
                            "/api/v1/documents/" + private["id"], headers=employee_headers
                        ).status_code
                        assert leaked == case["expected"]["leaked_source_count"]
                        assert direct == case["expected"]["direct_source_http_status"]
                        outcome["actual"] = {"leaked_source_count": leaked, "direct_status": direct}
                    elif case["suite"] == "business_correctness":
                        detail = client.get(
                            "/api/v1/metrics/forecast_margin/lineage", headers=owner_headers
                        ).json()
                        assert detail["metric"]["value"] == case["expected"]["forecast_margin"]
                        ids = sorted(r["id"] for r in detail["records"])
                        assert ids == sorted(case["expected"]["source_ids"])
                        outcome["actual"] = {
                            "forecast_margin": detail["metric"]["value"],
                            "source_ids": ids,
                        }
                    else:
                        provider = work.provider

                        class Failed:
                            def plan(self, *args):
                                raise DomainError("PROVIDER_UNAVAILABLE", 503)

                        work.provider = Failed()
                        before = count()
                        run = work.submit(
                            owner,
                            json.loads(Path(case["input_fixture"]).read_text()),
                            "eval-failure",
                            "eval",
                        )
                        work.process_one()
                        work.provider = provider
                        result = work.get(owner, run["id"])
                        assert result["state"] == case["expected"]["state"]
                        assert count() - before == case["expected"]["tasks_created"]
                        outcome["actual"] = {
                            "state": result["state"],
                            "tasks_created": count() - before,
                        }
                    outcome["status"] = "passed"
                    report["passed"] += 1
                except Exception as exc:
                    outcome["status"] = "failed"
                    outcome["error_type"] = type(exc).__name__
                    report["failed"] += 1
                outcome["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
                report["cases"].append(outcome)
        k.client.close()
        engine.dispose()
    socket.socket.connect = original
    Path(".runtime/eval-demo.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
