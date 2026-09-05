# AI Office engineering instructions

Preserve FastAPI, Pydantic, CrewAI, Ollama and Qdrant. This is a single-organization modular monolith with one worker, not a SaaS cluster.

- `uv sync --frozen --python 3.11`; `make lint`; `make test`; `make integration-test`; `make demo`; `make smoke`; `make eval-demo`.
- Keep business permissions, approval hashes and SQL transactions outside model adapters. Models never execute arbitrary tools, shell or external messages.
- Never index developer docs automatically. Never log prompts, documents, credentials or SDK replay contents.
- Do not commit .env, .runtime, credentials, business databases, uploads or model weights.
- Preserve the upstream repository; see docs/BASELINE_REVIEW.md. No distribution license has been selected.
- Hardware status stays “Target hardware; not yet validated on device.” until documented physical tests.
- Update IMPLEMENTATION_STATUS.md and app/capabilities.json with actual evidence. P1/P2 stays planned.
