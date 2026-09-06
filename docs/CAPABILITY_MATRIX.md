# Capability matrix

Implementation, validation, runtime mode and hardware evidence are independent. Hardware is never inferred from HTTP mock tests. Current customer-increment backend evidence was refreshed on 2026-09-07 (Europe/Moscow).

| Module | Implementation | Validation | Mode | Evidence | Limitations |
|---|---|---|---|---|---|
| Chief of Staff | implemented | integration | demo | tests/unit/test_workflows.py, tests/unit/test_task_assignments.py | Local tasks and unsent drafts only; individual assignments require explicit user selection |
| Knowledge | implemented | integration | demo | tests/security/test_knowledge.py, tests/security/test_document_formats.py | Text PDF, DOCX tables, TXT/Markdown; no OCR; bounded parser process is not an OS sandbox; hash demo embeddings do not validate semantic quality |
| Commercial proposals | implemented | integration | catalog_quote | tests/unit/test_quotes.py, tests/security/test_quote_security.py, tests/security/test_customer_api.py, scripts/customer_demo.py | RUB CSV/XLSX catalogs only; reviewed SKU/quantity suggestions; no outgoing sending; no statistical real-model quote-quality validation |
| Task assignments and deadlines | implemented | integration | stored_workflow_records | tests/unit/test_task_assignments.py, tests/security/test_customer_api.py, scripts/customer_demo.py | Existing local users and team visibility; on-demand briefing only; no scheduler or external notifications |
| Business Control | implemented | integration | synthetic | tests/unit/test_metrics.py | Fixture ledger, no live accounting source |
| Ollama + CrewAI | implemented | local_llm | local_ollama | tests/unit/test_providers.py, scripts/local_llm.py | Single installed-model planner/reviewer and embeddings check; repeated quality evaluation pending |
| Compatible HTTP | implemented | unit | compatible_http | tests/unit/test_providers.py | Runtime contract must be explicitly verified; no device claim |
| Investor Room, mail/CRM connectors, scheduled notifications | planned | not_run | roadmap | — | P1/P2; broader Office Manager workflows remain planned |
| Local AI Station 96–128 GB | partial | not_run | target_only | — | Vendor and runtime not selected; physical hardware validation pending; development does not require this station |

Seeded finance and supplied customer examples are synthetic. User uploads, catalogs and stored workflow tasks retain their actual origin. API/UI read app/capabilities.json; this document mirrors that registry. Local-model planning evidence from the earlier release does not prove new quote-generation quality. On-device status still requires physical evidence. See VALIDATION.md for command scope and timestamps.
