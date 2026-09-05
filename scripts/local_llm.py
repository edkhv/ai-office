"""Explicit opt-in measured local model check; never downloads weights or calls cloud."""

import json
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.contracts import Command
from app.providers import CrewProvider, embeddings_for


def main():
    root = Path(".runtime/local-llm")
    root.mkdir(parents=True, exist_ok=True)
    s = Settings(
        mode="local_ollama",
        embedding_provider="ollama",
        ollama_model="qwen3.5:9b",
        ollama_embedding_model="qwen3-embedding:latest",
        data_dir=root,
        _env_file=None,
    )
    # Restrict Python socket connects during the check to loopback; record attempts without payloads.
    connections = []
    connect = socket.socket.connect

    def local_only(sock, address):
        if isinstance(address, tuple):
            connections.append(str(address[0]))
            if address[0] not in {"127.0.0.1", "::1"}:
                raise RuntimeError("Non-local egress blocked during model check")
        return connect(sock, address)

    socket.socket.connect = local_only
    start = time.monotonic()
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "local_ollama",
        "model": s.ollama_model,
        "embedding_model": s.ollama_embedding_model,
        "hardware": "not_run",
        "tokens": None,
        "cost": None,
        "sample_count": 1,
        "passed": 0,
        "failed": 0,
    }
    try:
        p = CrewProvider(s)
        assert p.health() == "ready"
        command = Command(
            text="Collect three steel offers for North. Compare price, delivery, availability and payment deferral. Prepare a draft request, never send it. Use the confirmed team and deadline.",
            team_id="procurement",
            due_at="2026-09-11T15:00:00+03:00",
        )
        plan = p.plan(command, "local-llm-check")
        assert plan.proposed_tasks
        report["planning"] = "passed"
        report["task_count"] = len(plan.proposed_tasks)
        report["passed"] += 1
        emb, spec = embeddings_for(s)
        vectors = emb.embed_documents(
            ["Лимит закупок 100 000 рублей.", "Purchase approval threshold is 100000 RUB."]
        )
        assert len(vectors) == 2 and len(vectors[0]) == len(vectors[1]) > 0
        report["embeddings"] = "passed"
        report["dimensions"] = len(vectors[0])
        report["passed"] += 1
    except Exception as exc:
        report["failed"] += 1
        report["error_type"] = type(exc).__name__
        report["error_code"] = getattr(exc, "code", "LOCAL_CHECK_FAILED")
    finally:
        socket.socket.connect = connect
    report["latency_seconds"] = round(time.monotonic() - start, 3)
    report["connection_hosts"] = sorted(set(connections))
    Path(".runtime/local-llm-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
