# Baseline review — 2026-09-05

Read-only source: [edkhv/ai-docs-assistant](https://github.com/edkhv/ai-docs-assistant/tree/d24f1e98078009b89ee1a93eedc61bc1fc3be8f4). Actual cloned HEAD: `d24f1e98078009b89ee1a93eedc61bc1fc3be8f4`, matching the specification. The source checkout remains unmodified under ignored `.runtime/baseline`. It is not part of the new repository history. No LICENSE, AGENTS.md or third-party notice file was found. The upstream tests were read, not run; their success is not claimed.

Fully read: README, PROJECT_NOTES, all nine Python app files, both test modules, requirements, Dockerfile, Compose and tracked-file tree. The structural search plugin returned no symbols; direct complete reads were used.

| Source | Continuity | Change and reason | Verification |
|---|---|---|---|
| app/main.py | FastAPI, Pydantic routes, thread-safe sync route execution | App factory; authenticated /api/v1; durable jobs; safe errors; no network calls on import | test_api.py, smoke.py |
| app/agents.py | Generator → deterministic check → reviewer; CrewAI Agent/Task/Crew; exact `valid` | Typed plans and bounded custom local transport; model never approves or writes business data; SDK replay logging disabled | test_providers.py, test_workflows.py |
| app/rag.py | LangChain Document, OllamaEmbeddings, QdrantVectorStore | Immutable source versions, chunk metadata, SHA-256, collection fingerprint, SQL ACL filter before retrieval and recheck afterward; no startup reset | test_knowledge.py, test_qdrant.py |
| app/storage.py | Local persistence concept | Replaced slug/reservation/deletion with server-generated UUID/version names and O_EXCL/O_NOFOLLOW. Failed index versions stay recoverable | test_knowledge.py |
| app/health.py | Liveness, readiness and functional retrieval canary | Public status only; worker heartbeat and model availability; canary in integration tests and smoke | test_api.py, test_qdrant.py |
| app/schemas.py, settings.py | Pydantic v2, pydantic-settings | Strict request schemas and validated endpoint allowlist; no global Settings or client creation on import | test_api.py, test_providers.py |
| app/logger.py | Standard Python logging | Safe JSON metadata, no prompt/document/token/trace logging | test_api.py |
| requirements.txt | Same framework families | Real uv.lock; security-driven CrewAI update and compatible transitive resolution | dependency review, frozen installs, tests |
| Dockerfile, docker-compose.yml | Python 3.11, app and persistent Qdrant | Pinned images; init/API/worker from same image; loopback web port; private Qdrant; non-root app; isolated volumes | make demo, smoke, restart check |
| tests/test_endpoints.py, test_health.py | pytest, TestClient, isolation and canary approach | Expanded business state, ACL, idempotency, arithmetic and real Qdrant checks | tests/ |

This is architectural continuity, not a claim that upstream source files were copied verbatim. `my-api-docs` and upstream documentation content are not prerequisites. No LangGraph or alternate agent framework was added.

Dependency changes: FastAPI and supporting libraries resolved from compatible bounded ranges; CrewAI 1.7.2 was first exercised, then upgraded to 1.15.20 after pip-audit findings. Qdrant client remains 1.16.2 and the server uses v1.16.2. The custom CrewAI BaseLLM transport uses HTTPX directly, so the old direct LiteLLM 1.65.3 pin was removed; this prevents SDK provider routing from choosing an implicit cloud target. LangChain remains used for Qdrant and Ollama embeddings. Python 3.11 retained.

Docs checked: [CrewAI LLMs](https://docs.crewai.com/v1.15.20/en/concepts/llms), [LangChain Qdrant integration](https://docs.langchain.com/oss/python/integrations/vectorstores/qdrant), Context7 `/crewaiinc/crewai`, and installed-version source for BaseLLM calls, telemetry, trace consent and replay storage. These are API references, not evidence of Local AI Station compatibility.
