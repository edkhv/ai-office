"""Opt-in isolated local council check; synthetic inputs, safe metadata only."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings
from app.council import analyze, synthesize
from app.providers import CrewProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-url", default="http://127.0.0.1:18011")
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--output", default=".runtime/council-llm.json")
    args = parser.parse_args()
    provider = CrewProvider(
        Settings(
            _env_file=None,
            mode="local_ollama",
            data_mode="pilot",
            embedding_provider="ollama",
            agent_runtime_url=args.runtime_url,
            ollama_model=args.model,
        )
    )
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "synthetic_inputs": True,
        "model": args.model,
        "statistical_quality": "not_measured",
        "device_validation": "not_run",
        "checks": [],
    }
    question = "Стоит ли запускать пилот нового сервиса? Какие сведения ещё нужны для решения?"
    evidence = [
        {
            "source_id": "synthetic-pilot",
            "fragment": "Synthetic test: the team can spend two weeks testing a service idea. No customer demand evidence, confirmed budget or costs are available.",
        }
    ]
    perspectives = []
    for role in ("strategy", "finance", "critic", "synthesis"):
        start = time.monotonic()
        try:
            if role == "synthesis":
                result = synthesize(provider, question, perspectives, evidence)
                assert result["recommendation"] == "needs_data"
                detail = {
                    "recommendation": result["recommendation"],
                    "source_ids": result["source_ids"],
                }
            else:
                result = analyze(provider, question, role, evidence)
                perspectives.append(result)
                assert result["missing_data"]
                detail = {
                    "source_ids": result["source_ids"],
                    "missing_data_count": len(result["missing_data"]),
                }
            report["checks"].append(
                {
                    "stage": role,
                    "passed": True,
                    **detail,
                    "seconds": round(time.monotonic() - start, 2),
                }
            )
        except Exception as exc:
            report["checks"].append(
                {
                    "stage": role,
                    "passed": False,
                    "error_code": getattr(exc, "code", type(exc).__name__),
                    "seconds": round(time.monotonic() - start, 2),
                }
            )
        print(json.dumps(report["checks"][-1]), flush=True)
        Path(args.output).parent.mkdir(exist_ok=True, parents=True)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        if not report["checks"][-1]["passed"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
