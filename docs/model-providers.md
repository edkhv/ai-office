# Model providers

Demo: `engine=deterministic_demo`, model_id=null, hash/lexical embeddings. Only the procurement example is supported; unspecified assignment fields or unsupported requests ask for clarification. Knowledge answers in demo are extractive snippets. Quote suggestions match explicit known `SKU × quantity` expressions; other request text is not interpreted and requires manual review. This validates plumbing and policy, not model intelligence or semantic retrieval quality.

Ollama: set `AI_OFFICE_MODE=local_ollama`, `AI_OFFICE_EMBEDDING_PROVIDER=ollama`. Model and embedding identifiers are configurable; default examples are `qwen3:8b` and `mxbai-embed-large`. These are suggestions for development, not Local AI Station compatibility guarantees. No weights are downloaded by bootstrap.

Install Ollama and obtain the desired models separately through its documented distribution. Verify them with `ollama list`. Stop the demo before using the same port for the separate local profile:

```bash
make down
AI_OFFICE_OLLAMA_MODEL=qwen3.5:9b AI_OFFICE_OLLAMA_EMBEDDING_MODEL=qwen3-embedding:latest make local
docker compose -p ai-office-local -f compose.yaml -f compose.local.yaml exec app python -m app.cli credential owner
```

Use model names actually installed on your machine. The above pair was available on the development machine; it is not downloaded for users. The local profile uses distinct Compose volumes and host.docker.internal; Linux adds host-gateway. A successful macOS-host Ollama call does not verify arbitrary Linux, Windows or device installations. Stop it with the same Compose project and files followed by `down`; then `make demo` restores the demo profile.

CrewAI Planner and Reviewer are actual CrewAI steps. Each goes through a custom BaseLLM adapter using bounded HTTPX transport. The application validates TaskPlan before review and again before execution. Reviewer accepts exact `valid` after CrewAI parses the final answer; `invalid` is rejected. Parsing can perform one schema repair. There is no LangGraph, human_input terminal approval, autonomous delegation or model tool execution.

Transport rejects redirects, ignores proxy environment, limits time/output and uses only administrator-allowed hosts. Compatible HTTP calls `/chat/completions` and `/models` only after `AI_OFFICE_COMPATIBLE_CONTRACT_VERIFIED=true`, endpoint and model are set. It sends neither tool_calls nor response_format/streaming requests. It assumes no embeddings API; use separately configured Ollama embeddings. Authentication headers for a vendor API are not implemented; deploy behind a controlled local gateway if needed. Missing configuration reports not_configured, not ready.

CrewAI telemetry is disabled before import via OTEL_SDK_DISABLED and CREWAI_DISABLE_TELEMETRY, with tracing=False and project-local declined consent. A PrivateCrew override suppresses SDK content replay storage; stdout/stderr from kickoff are captured because SDK errors can otherwise echo prompts. No user-wide CrewAI preferences are changed. Socket-denial unit tests run actual CrewAI with mocked local HTTP. The opt-in measured script restricts Python socket connects to loopback; this is test evidence, not a universal firewall guarantee.

`uv run python scripts/local_llm.py` is an explicit installed-model check. Results, including an earlier rejected attempt, are documented in VALIDATION.md. It does not prove repeated statistical quality, factual entailment or device performance.

## Quote suggestions

The quote worker uses the same explicit local transport and schema-repair boundary to propose SKU/quantity/discount lines and accompanying prose. The server validates each SKU against the selected catalog; unknown items fail visibly. Real-model suggestions select explicit SKU candidates when possible and reject a context exceeding 100 catalog items or 12,000 serialized catalog characters. Oversized requests must be shortened explicitly instead of being silently interpreted only in part. Prices, VAT and totals are never accepted from the model. The UI presents suggestions for review before saving the exact quote and proposing a local task. Document text and catalog descriptions are untrusted input, with no model tools or outgoing business actions.

A saved suggestion run rechecks document/catalog access before returning its input/result. Provider/schema failures remain failed jobs and do not fall back to demo. The new quote-generation path has mocked-transport tests; the earlier installed-model Planner/Reviewer check does not establish real-model quote quality. Repeatable customer-specific evaluations remain pending.

## Isolated company pilot runtime

`AI_OFFICE_DATA_MODE=pilot` is independent of model mode: pilot+demo uses an empty company and deterministic extraction/SKU suggestions. It never creates the Northline procurement plan. Real pilot generation requires `AI_OFFICE_AGENT_RUNTIME_URL`; missing runtime fails closed rather than loading the SDK inside the core process.

`make pilot-local` adds the private CrewAI image and restricted model gateway from `compose.local.yaml`. The runtime receives only the current bounded model-step input, has no business-data volume, and belongs only to the internal inference network. The gateway exposes selected bounded model routes and does not proxy arbitrary requests. The core image excludes CrewAI/ChromaDB; the optional runtime retains four ChromaDB findings tracked separately.

The fresh opt-in [host](validation/pilot-isolated-llm-host.json) and [Docker](validation/pilot-isolated-llm-docker.json) checks each passed 4/5: health, sourced answer, explicit-SKU quote suggestion and embeddings passed; Planner/Reviewer rejected its sample. This confirms working model transports for those samples, not reliable free-form planning. Repeated customer-specific evaluation remains required.
