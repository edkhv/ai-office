"""Opt-in real model RPC checks using synthetic text; no business store or credentials."""

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.contracts import Command
from app.providers import CrewProvider, embeddings_for


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-url", default="http://agent-runtime:8001")
    parser.add_argument("--gateway-url", default="http://model-gateway:8002")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--embedding-model", default="qwen3-embedding")
    parser.add_argument("--output", default=".runtime/isolated-llm.json")
    args = parser.parse_args()
    evidence = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "synthetic_inputs": True,
        "model": args.model,
        "core_sdk_absent": all(
            importlib.util.find_spec(name) is None for name in ("crewai", "chromadb")
        ),
        "checks": [],
    }
    if not evidence["core_sdk_absent"]:
        raise RuntimeError("Run this check in the core environment without the agents extra")
    settings = Settings(
        _env_file=None,
        mode="local_ollama",
        data_mode="pilot",
        embedding_provider="ollama",
        agent_runtime_url=args.runtime_url,
        ollama_base_url=args.gateway_url,
        ollama_model=args.model,
        ollama_embedding_model=args.embedding_model,
        provider_timeout=60,
    )
    provider = CrewProvider(settings)
    original_step = provider.crew_step

    def observed_step(role, instruction):
        result = original_step(role, instruction)
        if role == "Reviewer":
            verdict = result.strip().lower()
            evidence["reviewer_verdict_category"] = (
                verdict if verdict in {"valid", "invalid"} else "non_exact_verdict"
            )
        return result

    provider.crew_step = observed_step

    def check(name, action):
        started = datetime.now(UTC)
        try:
            details = action()
            evidence["checks"].append({"name": name, "passed": True, "details": details})
            print(name + ": passed", flush=True)
        except Exception as exc:
            evidence["checks"].append(
                {
                    "name": name,
                    "passed": False,
                    "error_type": type(exc).__name__,
                    "error_code": getattr(exc, "code", "CHECK_FAILED"),
                }
            )
            print(name + ": failed (" + type(exc).__name__ + ")", flush=True)
        evidence["checks"][-1]["seconds"] = (datetime.now(UTC) - started).total_seconds()
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(evidence, indent=2) + "\n")

    def health():
        assert provider.health() == "ready"
        return {"ready": True}

    def plan():
        command = Command(
            text="Collect three steel supply offers and compare price, delivery and payment terms. Propose local tasks only.",
            team_id="procurement",
            due_at="2026-10-01T10:00:00+03:00",
        )
        result = provider.plan(command, "synthetic-rpc-check")
        assert result.proposed_tasks and result.source_ref == "synthetic-rpc-check"
        return {"tasks": len(result.proposed_tasks), "reviewer_accepted": True}

    def answer():
        result = provider.answer(
            "What is the approved budget?",
            [
                {
                    "source_id": "synthetic-budget",
                    "fragment": "The approved project budget is 100000 RUB.",
                }
            ],
        )
        assert not result.insufficient_evidence and "synthetic-budget" in result.source_ids
        return {"source_ids": result.source_ids}

    def quote():
        result = provider.suggest_quote(
            "Please quote 3 units of SKU STEEL-01.",
            [{"sku": "STEEL-01", "name": "Steel sheet", "unit": "piece"}],
        )
        assert result["lines"] and result["lines"][0]["sku"] == "STEEL-01"
        assert float(result["lines"][0]["quantity"]) == 3
        return {"matched_lines": len(result["lines"])}

    def embeddings():
        model, _ = embeddings_for(settings)
        vectors = model.embed_documents(["Approved synthetic budget", "Synthetic steel request"])
        assert len(vectors) == 2 and len(vectors[0]) > 0
        return {"vectors": len(vectors), "dimensions": len(vectors[0])}

    for name, action in (
        ("runtime_health", health),
        ("planner_and_reviewer", plan),
        ("grounded_answer", answer),
        ("quote_suggestion", quote),
        ("gateway_embeddings", embeddings),
    ):
        check(name, action)
    print(json.dumps(evidence, indent=2), flush=True)
    return 0 if all(item["passed"] for item in evidence["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
