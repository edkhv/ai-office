# MVP scope

P0 implemented: web/API, local credentials and scoped sessions, SQLite migrations, durable jobs and worker leases, executive instruction→typed proposal→approval→local tasks, job/history polling, status updates, Markdown/TXT versioned ingestion, Qdrant ACL retrieval and evidence links, five Decimal metrics with lineage, on-demand briefing, safe audit, demo/Ollama/compatible HTTP providers, bilingual UI, tests/evals and partner materials.

Constraints: the demo supports the procurement scenario only; structured team/date/time fields must be explicitly confirmed even when mentioned in free text. Real model suggestions are not automatically authoritative. No supplier message is sent. No live business connector exists; financial records remain synthetic even in local-LLM mode. Retrieval is dense/hash-based without a hybrid index or reranker. Owner CLI reindex may need explicit source ACL grants. Hardware runtime is not installed or verified. Read DEPENDENCY_REVIEW before a real-data pilot.

The app/API/README use the same capability matrix. Validation may be unit, integration or local_llm while device validation remains not_run. Deferred scope must not be presented as optional P0 work already completed.
