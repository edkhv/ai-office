"""Exercise live API + separate worker + Qdrant; print no credentials or private data."""

import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8090"
COMMAND = {
    "text": "Collect three steel offers for project North. Compare price, delivery, availability and payment deferral. Prepare an unsent supplier draft.",
    "team_id": "procurement",
    "due_at": "2026-09-11T15:00:00+03:00",
}


def demo_token(role="owner"):
    return subprocess.check_output(
        ["docker", "compose", "exec", "-T", "app", "cat", f"/data/{role}.token"], text=True
    ).strip()


def wait_run(client, run_id, states, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = client.get(f"/api/v1/runs/{run_id}")
        r.raise_for_status()
        result = r.json()
        if result["state"] in states:
            return result
        if result["state"] == "failed":
            raise AssertionError("Live workflow failed: " + result["result"]["error_code"])
        time.sleep(0.25)
    raise AssertionError("Workflow timed out; inspect worker and saved job status")


def main():
    start = time.monotonic()
    checks = []
    with httpx.Client(
        base_url=BASE,
        timeout=15,
        trust_env=False,
        headers={"Authorization": "Bearer " + demo_token()},
    ) as client:
        client.get("/health/ready").raise_for_status()
        checks.append("ready")
        key = str(uuid.uuid4())
        response = client.post("/api/v1/commands", headers={"Idempotency-Key": key}, json=COMMAND)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        run = wait_run(client, run_id, {"awaiting_approval"})
        task_rows = client.get("/api/v1/tasks?limit=100").json()
        assert not any(t["source_run_id"] == run_id for t in task_rows)
        checks.append("no_tasks_before_approval")
        assert (
            client.post("/api/v1/commands", headers={"Idempotency-Key": key}, json=COMMAND).json()[
                "run_id"
            ]
            == run_id
        )
        proposal = run["proposal"]
        decision = {
            "decision": "approve",
            "version": proposal["version"],
            "payload_hash": proposal["payload_hash"],
        }
        url = "/api/v1/approvals/" + proposal["id"] + "/decision"
        client.post(url, json=decision).raise_for_status()
        client.post(url, json=decision).raise_for_status()
        wait_run(client, run_id, {"completed"})
        task_rows = client.get("/api/v1/tasks?limit=100").json()
        own = [t for t in task_rows if t["source_run_id"] == run_id]
        assert len(own) == 3
        checks.append("approved_exactly_three_local_tasks")
        client.patch(
            "/api/v1/tasks/" + own[0]["id"],
            json={"status": "in_progress", "result": "Synthetic comparison in preparation."},
        ).raise_for_status()
        question = client.post(
            "/api/v1/knowledge/ask",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            json={"query": "лимит самостоятельного согласования закупок"},
        )
        question.raise_for_status()
        answer = wait_run(client, question.json()["run_id"], {"completed"})["result"]
        assert answer["evidence"] and "100 000" in answer["answer"]
        for ref in answer["evidence"]:
            client.get(ref["url"]).raise_for_status()
        checks.append("retrieval_answer_and_citations")
        expected = {
            "cash_balance": "2300000.00",
            "overdue_receivables": "450000.00",
            "forecast_profit": "360000.00",
            "forecast_margin": "20.00",
            "price_change": "14.00",
        }
        for metric in client.get("/api/v1/metrics").json():
            assert metric["value"] == expected[metric["metric_id"]]
            detail = client.get("/api/v1/metrics/" + metric["metric_id"] + "/lineage").json()
            assert {x["record_id"] for x in metric["input_refs"]} == {
                r["id"] for r in detail["records"]
            }
        checks.append("five_metrics_and_resolved_lineage")
        client.post("/api/v1/briefings").raise_for_status()
        assert client.get("/api/v1/audit").json()
        assert (
            client.get("/api/v1/system/capabilities").json()["hardware"]["validation"] == "not_run"
        )
        checks.append("briefing_audit_hardware_boundary")
    with httpx.Client(
        base_url=BASE,
        trust_env=False,
        headers={"Authorization": "Bearer " + demo_token("employee")},
    ) as employee:
        assert employee.get("/api/v1/metrics").status_code == 403
        assert employee.get("/api/v1/runs/" + run_id).status_code == 404
    checks.append("live_role_scopes")
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "demo",
        "checks": checks,
        "passed": len(checks),
        "failed": 0,
        "duration_seconds": round(time.monotonic() - start, 3),
        "run_id": run_id,
    }
    Path(".runtime").mkdir(exist_ok=True)
    Path(".runtime/smoke.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
